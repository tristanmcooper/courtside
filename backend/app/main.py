"""Courtside backend: ingest sensor + wearable data, serve the live dashboard."""
import os
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Body
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, desc, func

from .db import (Base, engine, SessionLocal, CourtReading, HealthDaily,
                 Session as SessionModel, Workout, ensure_columns)
from .schemas import CourtIn, SessionIn

# If NODE_KEY is set, /ingest/court requires a matching X-Node-Key header.
# Left empty in local dev so curl/testing works without a key.
NODE_KEY = os.getenv("NODE_KEY", "")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Courtside")
Base.metadata.create_all(engine)
ensure_columns()  # add any newly-added model columns to existing tables


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
_RESP_NAMES = {"respiratory_rate"}


def _day_of(point: dict) -> Optional[str]:
    d = point.get("date") or point.get("startDate") or point.get("sleepStart")
    return str(d)[:10] if d else None


def _num(point: dict, *keys):
    for k in keys:
        v = point.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _wq(obj):
    """HAE values may be a number or a {'qty': .., 'units': ..} object."""
    if isinstance(obj, dict):
        return obj.get("qty") if isinstance(obj.get("qty"), (int, float)) else None
    return obj if isinstance(obj, (int, float)) else None


def _wts(s):
    """Parse a HAE timestamp like '2026-06-04 14:00:00 -0700' to naive UTC."""
    if not s:
        return None
    try:
        from datetime import datetime as _dt
        d = _dt.strptime(str(s).strip(), "%Y-%m-%d %H:%M:%S %z")
        return d.astimezone(timezone.utc).replace(tzinfo=None)
    except Exception:
        try:
            return datetime.fromisoformat(str(s)[:19])
        except Exception:
            return None


def parse_workout(w: dict) -> dict:
    """Defensive extraction across HAE versions; full object kept in raw."""
    hr_list = w.get("heartRateData") or w.get("heartRate") or []
    hrs = [_wq(p) for p in hr_list if isinstance(p, dict)] if isinstance(hr_list, list) else []
    hrs = [h for h in hrs if h is not None]
    return {
        "name": w.get("name") or w.get("workoutActivityType") or w.get("type"),
        "start_ts": _wts(w.get("start") or w.get("startDate")),
        "end_ts": _wts(w.get("end") or w.get("endDate")),
        "duration_min": (_wq(w.get("duration")) or 0) / 60.0 if _wq(w.get("duration")) else None,
        "active_energy": _wq(w.get("activeEnergyBurned") or w.get("activeEnergy")),
        "avg_hr": _wq(w.get("avgHeartRate") or w.get("averageHeartRate")) or (sum(hrs) / len(hrs) if hrs else None),
        "max_hr": _wq(w.get("maxHeartRate")) or (max(hrs) if hrs else None),
        "distance_m": _wq(w.get("distance") or w.get("totalDistance")),
    }


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
            slot = by_day.setdefault(day, {"raw": {}})
            qty = _num(point, "qty", "value", "Avg", "avg", "asleep", "totalSleep")
            if qty is not None:
                slot["raw"][name] = qty          # lossless: keep every metric HAE sent
            if name in _HRV_NAMES and qty is not None:
                slot["hrv_sdnn"] = qty
            elif name in _RHR_NAMES and qty is not None:
                slot["resting_hr"] = qty
            elif name in _RESP_NAMES and qty is not None:
                slot["respiratory_rate"] = qty
            elif name in _SLEEP_NAMES:
                sv = _num(point, "asleep", "totalSleep", "value", "qty", "asleepUnspecified")
                if not sv:   # 0 or None -> sum the asleep stages (HAE v2 shape)
                    sv = sum(point[k] for k in ("core", "deep", "rem", "asleepUnspecified")
                             if isinstance(point.get(k), (int, float)))
                if sv:
                    slot["sleep_hours"] = float(sv)
                slot["raw"]["sleep_analysis"] = {k: v for k, v in point.items() if k != "date"}

    db = SessionLocal()
    written = 0
    try:
        for day_str, vals in by_day.items():
            raw = vals.pop("raw", {})
            if not vals and not raw:
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
            existing.raw = raw
            written += 1

        # workouts (Data Type = Workouts posts to this same endpoint)
        workouts = (payload.get("data") or payload).get("workouts", []) or []
        w_written = 0
        for w in workouts:
            f = parse_workout(w)
            if f["start_ts"] is None:
                continue
            existing = db.execute(
                select(Workout).where(Workout.start_ts == f["start_ts"])
            ).scalar_one_or_none()
            if existing is None:
                existing = Workout(start_ts=f["start_ts"], source="apple")
                db.add(existing)
            for k, v in f.items():
                if v is not None:
                    setattr(existing, k, v)
            existing.raw = w
            w_written += 1

        db.commit()
    finally:
        db.close()
    return {"ok": True, "days_written": written, "workouts_written": w_written,
            "metrics_seen": sorted(seen)}


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
_FIELDS = (
    "day", "start_ts", "end_ts", "location", "lat", "lon", "partner", "opponent_level",
    "subjective_rating_1_10", "peer_rating_1_10", "coach_rating_1_10", "wind_self_report",
    "felt_state", "kills", "errors", "sets_won", "sets_lost", "notes", "status",
)


def _apply(row, s: SessionIn):
    for f in _FIELDS:
        v = getattr(s, f, None)
        if v is not None:
            setattr(row, f, v)


def _session_dict(s) -> dict:
    return {f: getattr(s, f) for f in ("session_id",) + _FIELDS}


def _court_window(db, start, end):
    q = select(CourtReading).order_by(CourtReading.server_ts)
    if start is not None:
        q = q.where(CourtReading.server_ts >= start)
    if end is not None:
        q = q.where(CourtReading.server_ts <= end)
    return db.execute(q).scalars().all()


def _aggregate(readings) -> dict:
    def mm(attr):
        v = [getattr(r, attr) for r in readings if getattr(r, attr) is not None]
        return {"mean": round(sum(v) / len(v), 2), "min": round(min(v), 2),
                "max": round(max(v), 2)} if v else None
    return {"sand_temp": mm("ir_object_c"), "air_temp": mm("temp_c"),
            "humidity": mm("humidity_pct"), "wind_sound": mm("sound_pp")}


@app.post("/api/sessions/start")
def start_session():
    """Begin recording — bookmarks the start so the session's sensor window is known."""
    db = SessionLocal()
    try:
        now = utcnow()
        base = now.strftime("%Y-%m-%d_%H%M%S")
        sid, n = base, 2
        while db.get(SessionModel, sid) is not None:   # avoid same-second collisions
            sid, n = f"{base}-{n}", n + 1
        db.add(SessionModel(session_id=sid, day=now.date(), start_ts=now, status="recording"))
        db.commit()
        return {"ok": True, "session_id": sid, "start_ts": now.isoformat() + "Z"}
    finally:
        db.close()


@app.post("/api/sessions/{sid}/stop")
def stop_session(sid: str, s: SessionIn):
    """End recording (server stamps end_ts) and attach the evaluation fields."""
    db = SessionLocal()
    try:
        row = db.get(SessionModel, sid)
        if not row:
            raise HTTPException(404, "no such session")
        row.end_ts = utcnow()
        row.status = "done"
        _apply(row, s)
        db.commit()
        return {"ok": True, "session_id": sid}
    finally:
        db.close()


@app.post("/api/sessions")
def create_session(s: SessionIn):
    """Create/upsert a fully-specified session (manual log, no live recording)."""
    db = SessionLocal()
    try:
        day = s.day or (s.start_ts.date() if s.start_ts else date.today())
        sid = s.session_id or f"{day.isoformat()}_{datetime.now().strftime('%H%M')}"
        row = db.get(SessionModel, sid) or SessionModel(session_id=sid)
        row.day = day
        _apply(row, s)
        db.add(row)
        db.commit()
        return {"ok": True, "session_id": sid}
    finally:
        db.close()


@app.patch("/api/sessions/{sid}")
def patch_session(sid: str, s: SessionIn):
    db = SessionLocal()
    try:
        row = db.get(SessionModel, sid)
        if not row:
            raise HTTPException(404, "no such session")
        _apply(row, s)
        db.commit()
        return {"ok": True, "session_id": sid}
    finally:
        db.close()


@app.delete("/api/sessions/{sid}")
def delete_session(sid: str):
    db = SessionLocal()
    try:
        row = db.get(SessionModel, sid)
        if row:
            db.delete(row)
            db.commit()
        return {"ok": True}
    finally:
        db.close()


@app.get("/api/sessions")
def list_sessions():
    db = SessionLocal()
    try:
        rows = db.execute(select(SessionModel).order_by(desc(SessionModel.day))).scalars().all()
        return [
            {"session_id": r.session_id, "day": r.day.isoformat(), "status": r.status,
             "subjective_rating_1_10": r.subjective_rating_1_10,
             "peer_rating_1_10": r.peer_rating_1_10, "coach_rating_1_10": r.coach_rating_1_10,
             "kills": r.kills, "errors": r.errors, "partner": r.partner,
             "location": r.location, "notes": r.notes,
             "sensors": _aggregate(_court_window(db, r.start_ts, r.end_ts)) if r.start_ts else {}}
            for r in rows
        ]
    finally:
        db.close()


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    db = SessionLocal()
    try:
        row = db.get(SessionModel, sid)
        if not row:
            raise HTTPException(404, "no such session")
        d = _session_dict(row)
        readings = _court_window(db, row.start_ts, row.end_ts)
        d["sensors"] = _aggregate(readings)
        d["n_readings"] = len(readings)
        return d
    finally:
        db.close()


@app.get("/api/sessions/{sid}/readings")
def session_readings(sid: str):
    db = SessionLocal()
    try:
        row = db.get(SessionModel, sid)
        if not row:
            raise HTTPException(404, "no such session")
        readings = _court_window(db, row.start_ts, row.end_ts)
        return {"count": len(readings), "readings": [_reading_dict(r) for r in readings]}
    finally:
        db.close()


@app.get("/api/summary")
def summary():
    db = SessionLocal()
    try:
        sessions = db.execute(select(SessionModel).order_by(SessionModel.day)).scalars().all()
        rated = [s for s in sessions if s.subjective_rating_1_10 is not None]
        ratings = [s.subjective_rating_1_10 for s in rated]
        n_court = db.execute(select(func.count()).select_from(CourtReading)).scalar()
        return {
            "n_sessions": len(sessions),
            "n_rated": len(rated),
            "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
            "best_rating": max(ratings) if ratings else None,
            "worst_rating": min(ratings) if ratings else None,
            "n_court_readings": n_court,
            "history": [
                {"day": s.day.isoformat(), "session_id": s.session_id,
                 "rating": s.subjective_rating_1_10, "peer": s.peer_rating_1_10,
                 "coach": s.coach_rating_1_10}
                for s in rated
            ],
        }
    finally:
        db.close()


# ------------------------------------------------------------------- export API
@app.get("/api/export")
def export_all():
    """Full dump for the offline analysis pipeline (build_features.py)."""
    db = SessionLocal()
    try:
        courts = db.execute(select(CourtReading).order_by(CourtReading.server_ts)).scalars().all()
        sessions = db.execute(select(SessionModel).order_by(SessionModel.day)).scalars().all()
        health = db.execute(select(HealthDaily).order_by(HealthDaily.day)).scalars().all()
        workouts = db.execute(select(Workout).order_by(Workout.start_ts)).scalars().all()
        return {
            "court_readings": [_reading_dict(r) for r in courts],
            "sessions": [
                {col.name: getattr(s, col.name) for col in SessionModel.__table__.columns}
                for s in sessions
            ],
            "health_daily": [
                {"day": h.day.isoformat(), "source": h.source, "hrv_sdnn": h.hrv_sdnn,
                 "resting_hr": h.resting_hr, "sleep_hours": h.sleep_hours,
                 "respiratory_rate": h.respiratory_rate, "raw": h.raw}
                for h in health
            ],
            "workouts": [
                {"name": w.name,
                 "start_ts": w.start_ts.isoformat() if w.start_ts else None,
                 "end_ts": w.end_ts.isoformat() if w.end_ts else None,
                 "duration_min": w.duration_min, "active_energy": w.active_energy,
                 "avg_hr": w.avg_hr, "max_hr": w.max_hr, "distance_m": w.distance_m}
                for w in workouts
            ],
        }
    finally:
        db.close()


# -------------------------------------------------------------------- dashboard
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))




# ##/*
# # yes build the workout. should i first find a workout to send so you know the format? also why is there a main thing that shows sand surface temp but then theres another that shows sand IR? seems redundant? also why is only sand surface have a thing? makes it look like sand is the whole point. i'm not saying it looks bad but just wondering. also are we pulling from weather api too? shouldn't there be that too? or is that too much infomration. maybe we should partition based on sensor readings and weather api readings idk? should there be a physical summary or no is that too much and outside of our scope. also courside font for the title is too basic. maybe generate a png and put it there so it looks more professional? if you need me to do it i can.# Courtside UI Concept Correction



# The app is not a sand-temperature dashboard. It is a multi-modal beach volleyball session logger that combines:



# 1. subjective performance outcome

# 2. courtside environmental sensor data

# 3. wearable recovery/physiology data

# 4. contextual player/session notes

# 5. factor-ranking analysis



# Primary product promise:

# "What factors likely explained today's performance?"



# ## Main UI hierarchy

# Prioritize:

# 1. session rating / outcome

# 2. wind + recovery + mental/physical state

# 3. environmental sensor readings

# 4. wearable context

# 5. trend/factor-ranking insights



# Do not visually center the whole app around sand temperature.



# ## Record screen

# Hero should be "Session Capture" or "Court Conditions", not "Sand Surface".



# Use balanced sensor cards:

# - Surface Temp

# - Air Temp

# - Humidity

# - Wind Proxy



# Remove duplicated "Sand Surface" + "Sand IR".

# Use "Surface Temp" as user-facing label.

# Keep "IR Sensor" only in debug/details.



# ## Add Player State section

# Include lightweight subjective inputs:

# - Energy

# - Soreness

# - Mental state

# - Food timing

# - Warm-up quality

# - Notes



# This is in-scope because player survey feedback emphasized recovery, tiredness, mental state, food, soreness, and warm-up quality.



# Keep it low-burden.



# ## Add Wearable Context section

# Show Oura/Apple Watch data when available:

# - Sleep score

# - Readiness score

# - Activity score

# - HR data if Apple Watch HealthKit export exists



# Do not fake live wearable syncing. Label source clearly.



# ## Weather API

# Weather API is secondary context only.



# Separate:

# - On-court sensor readings

# - Local weather context



# Weather can include:

# - UV

# - forecast wind

# - general condition

# - outdoor temp



# Do not mix weather API values with local sensor readings.



# ## Insights screen

# Focus on factor ranking:

# - Best session

# - Average self rating

# - Trend

# - Top likely factors

# - Rating vs wind

# - Rating vs recovery

# - Rating vs surface temp

# - Rating vs sleep/readiness



# Avoid overclaiming with small N.

# Use language like:

# "Possible factor"

# "Associated with"

# "Not enough sessions yet"



# ## Final product feel

# Premium Oura-style interface, but for beach volleyball performance.



# The UI should answer:

# "How did I play, what were the conditions, how was my body, and what probably mattered?"
# # 
# # */
