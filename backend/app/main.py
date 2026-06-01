"""Courtside backend: ingest sensor + wearable data, serve the live dashboard."""
import os
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Body
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, desc

from .db import Base, engine, SessionLocal, CourtReading, HealthDaily, Session as SessionModel
from .schemas import CourtIn, SessionIn

# If NODE_KEY is set, /ingest/court requires a matching X-Node-Key header.
# Left empty in local dev so curl/testing works without a key.
NODE_KEY = os.getenv("NODE_KEY", "")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Courtside")
Base.metadata.create_all(engine)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _reading_dict(r: CourtReading) -> dict:
    return {
        "node_id": r.node_id,
        "server_ts": r.server_ts.isoformat() + "Z",
        "device_millis": r.device_millis,
        "temp_c": r.temp_c,
        "humidity_pct": r.humidity_pct,
        "pressure_hpa": r.pressure_hpa,
        "ir_object_c": r.ir_object_c,
        "ir_ambient_c": r.ir_ambient_c,
        "sound_pp": r.sound_pp,
    }


# ---------------------------------------------------------------- ingest: court
@app.post("/ingest/court")
def ingest_court(reading: CourtIn, x_node_key: Optional[str] = Header(default=None)):
    if NODE_KEY and x_node_key != NODE_KEY:
        raise HTTPException(status_code=401, detail="bad node key")
    db = SessionLocal()
    try:
        row = CourtReading(
            node_id=reading.node_id or "court-node-1",
            server_ts=utcnow(),
            device_millis=reading.device_millis,
            temp_c=reading.temp_c,
            humidity_pct=reading.humidity_pct,
            pressure_hpa=reading.pressure_hpa,
            ir_object_c=reading.ir_object_c,
            ir_ambient_c=reading.ir_ambient_c,
            sound_pp=reading.sound_pp,
        )
        db.add(row)
        db.commit()
        return {"ok": True, "id": row.id}
    finally:
        db.close()


# --------------------------------------------------------------- ingest: health
# Tolerant parser for Health Auto Export's "REST API" JSON payload.
_HRV_NAMES = {"heart_rate_variability", "hrv", "heart_rate_variability_sdnn"}
_RHR_NAMES = {"resting_heart_rate"}
_SLEEP_NAMES = {"sleep_analysis"}


def _day_of(point: dict) -> Optional[str]:
    d = point.get("date") or point.get("startDate") or point.get("sleepStart")
    return str(d)[:10] if d else None


def _num(point: dict, *keys):
    for k in keys:
        v = point.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return None


@app.post("/ingest/health")
def ingest_health(payload: dict = Body(...)):
    metrics = (payload.get("data") or payload).get("metrics", [])
    by_day: dict[str, dict] = {}
    seen: set[str] = set()

    for metric in metrics:
        name = str(metric.get("name", "")).lower()
        seen.add(name)
        for point in metric.get("data", []):
            day = _day_of(point)
            if not day:
                continue
            slot = by_day.setdefault(day, {})
            if name in _HRV_NAMES:
                v = _num(point, "qty", "value", "Avg", "avg")
                if v is not None:
                    slot["hrv_sdnn"] = v
            elif name in _RHR_NAMES:
                v = _num(point, "qty", "value")
                if v is not None:
                    slot["resting_hr"] = v
            elif name in _SLEEP_NAMES:
                v = _num(point, "asleep", "totalSleep", "value", "qty")
                if v is not None:
                    slot["sleep_hours"] = v

    db = SessionLocal()
    written = 0
    try:
        for day_str, vals in by_day.items():
            if not vals:
                continue
            day = date.fromisoformat(day_str)
            existing = db.execute(
                select(HealthDaily).where(HealthDaily.day == day, HealthDaily.source == "apple")
            ).scalar_one_or_none()
            if existing is None:
                existing = HealthDaily(day=day, source="apple")
                db.add(existing)
            for k, v in vals.items():
                setattr(existing, k, v)
            existing.raw = vals
            written += 1
        db.commit()
    finally:
        db.close()
    return {"ok": True, "days_written": written, "metrics_seen": sorted(seen)}


# ------------------------------------------------------------------- read APIs
@app.get("/api/live")
def api_live():
    db = SessionLocal()
    try:
        row = db.execute(
            select(CourtReading).order_by(desc(CourtReading.server_ts)).limit(1)
        ).scalar_one_or_none()
        if not row:
            return {"online": False, "age_s": None, "reading": None}
        age = (utcnow() - row.server_ts).total_seconds()
        return {"online": age <= 10, "age_s": round(age, 1), "reading": _reading_dict(row)}
    finally:
        db.close()


@app.get("/api/court/recent")
def api_recent(minutes: int = 5):
    db = SessionLocal()
    try:
        cutoff = utcnow() - timedelta(minutes=minutes)
        rows = db.execute(
            select(CourtReading).where(CourtReading.server_ts >= cutoff).order_by(CourtReading.server_ts)
        ).scalars().all()
        return {"count": len(rows), "readings": [_reading_dict(r) for r in rows]}
    finally:
        db.close()


# ----------------------------------------------------------------- sessions API
@app.post("/api/sessions")
def create_session(s: SessionIn):
    db = SessionLocal()
    try:
        day = s.day or (s.start_ts.date() if s.start_ts else date.today())
        sid = s.session_id or f"{day.isoformat()}_{datetime.now().strftime('%H%M')}"
        row = db.get(SessionModel, sid) or SessionModel(session_id=sid)
        row.day = day
        for field in (
            "start_ts", "end_ts", "location", "lat", "lon", "partner",
            "opponent_level", "subjective_rating_1_10", "wind_self_report",
            "felt_state", "kills", "errors", "sets_won", "sets_lost", "notes",
        ):
            val = getattr(s, field)
            if val is not None:
                setattr(row, field, val)
        db.add(row)
        db.commit()
        return {"ok": True, "session_id": sid}
    finally:
        db.close()


@app.get("/api/sessions")
def list_sessions():
    db = SessionLocal()
    try:
        rows = db.execute(select(SessionModel).order_by(desc(SessionModel.day))).scalars().all()
        return [
            {
                "session_id": r.session_id, "day": r.day.isoformat(),
                "subjective_rating_1_10": r.subjective_rating_1_10,
                "kills": r.kills, "errors": r.errors, "partner": r.partner,
                "location": r.location, "notes": r.notes,
            }
            for r in rows
        ]
    finally:
        db.close()


# -------------------------------------------------------------------- dashboard
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))
