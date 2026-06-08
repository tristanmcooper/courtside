"""Courtside backend: ingest sensor + wearable data, serve the live dashboard."""
import os
import re
import math
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Body
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, desc, func

from .db import (Base, engine, SessionLocal, CourtReading, HealthDaily,
                 Session as SessionModel, Workout, Person, SessionPerson, ensure_columns)
from .schemas import CourtIn, SessionIn, PersonIn

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
    "energy_1_5", "soreness_1_5", "mental_1_5", "warmup_1_5", "food_timing",
    "felt_state", "kills", "errors", "sets_won", "sets_lost", "notes", "status",
)


def _has_workout(db, start, end) -> bool:
    """True if an Apple Watch workout overlaps the session's [start, end] window."""
    if start is None or end is None:
        return False
    n = db.execute(
        select(func.count()).select_from(Workout)
        .where(Workout.start_ts <= end, Workout.end_ts >= start)
    ).scalar()
    return bool(n)


def _apply(row, s: SessionIn):
    for f in _FIELDS:
        v = getattr(s, f, None)
        if v is not None:
            setattr(row, f, v)


def _session_dict(s) -> dict:
    return {f: getattr(s, f) for f in ("session_id",) + _FIELDS}


# ------------------------------------------------------------------ people / personas
_PERSON_COLORS = ["#67e8d1", "#f6b26b", "#9db8ff", "#f4a4c0", "#a6e3a1",
                  "#ffd29a", "#c4b5fd", "#7dd3fc", "#fca5a5", "#5ad19a"]


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return s or "person"


def _get_or_create_person(db, name: str, kind: str = "both"):
    name = (name or "").strip()
    if not name:
        return None
    pid = _slug(name)
    p = db.get(Person, pid)
    if p is None:
        color = _PERSON_COLORS[sum(ord(c) for c in pid) % len(_PERSON_COLORS)]
        p = Person(id=pid, name=name, kind=kind, color=color, created_at=utcnow())
        db.add(p)
    elif kind != "both" and p.kind not in (kind, "both"):
        p.kind = "both"   # they've now been both a partner and an opponent
    return p


def _sync_session_people(db, sid: str, partner: Optional[str], opponents):
    """Replace a session's people links from the submitted partner + opponents."""
    if partner is None and opponents is None:
        return
    if partner is not None:
        db.execute(SessionPerson.__table__.delete().where(
            (SessionPerson.session_id == sid) & (SessionPerson.role == "partner")))
        p = _get_or_create_person(db, partner, "partner")
        if p:
            db.add(SessionPerson(session_id=sid, person_id=p.id, role="partner"))
    if opponents is not None:
        db.execute(SessionPerson.__table__.delete().where(
            (SessionPerson.session_id == sid) & (SessionPerson.role == "opponent")))
        for nm in opponents:
            p = _get_or_create_person(db, nm, "opponent")
            if p:
                db.add(SessionPerson(session_id=sid, person_id=p.id, role="opponent"))


def _people_for_session(db, sid: str) -> dict:
    rows = db.execute(select(SessionPerson).where(SessionPerson.session_id == sid)).scalars().all()
    out = {"partners": [], "opponents": []}
    for r in rows:
        p = db.get(Person, r.person_id)
        if not p:
            continue
        entry = {"id": p.id, "name": p.name, "color": p.color}
        out["partners" if r.role == "partner" else "opponents"].append(entry)
    return out


# ---- small-N significance test (pure Python; no scipy on the web service) ----
def _betacf(a, b, x):
    MAXIT, EPS, FPMIN = 200, 3e-7, 1e-30
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < EPS:
            break
    return h


def _betai(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    bt = math.exp(lbeta + a * math.log(x) + b * math.log(1.0 - x))
    return bt * _betacf(a, b, x) / a if x < (a + 1) / (a + b + 2) else 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _welch_p(a, b):
    """Two-sided Welch's t-test p-value for two small samples; None if degenerate."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return None
    ma, mb = sum(a) / na, sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    se2 = va / na + vb / nb
    if se2 <= 0:
        return None
    t = (ma - mb) / math.sqrt(se2)
    df = se2 ** 2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    if df <= 0:
        return None
    return _betai(df / 2.0, 0.5, df / (df + t * t))


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
        _sync_session_people(db, sid, s.partner, s.opponents)
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
        db.flush()
        _sync_session_people(db, sid, s.partner, s.opponents)
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
        _sync_session_people(db, sid, s.partner, s.opponents)
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
            db.execute(SessionPerson.__table__.delete().where(SessionPerson.session_id == sid))
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
             "has_workout": _has_workout(db, r.start_ts, r.end_ts),
             "people": _people_for_session(db, r.session_id),
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
        d["has_workout"] = _has_workout(db, row.start_ts, row.end_ts)
        d["people"] = _people_for_session(db, sid)
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
def _health_for_day(db, day):
    """Wearable recovery values recorded on a session's calendar day (any source)."""
    if day is None:
        return {}
    rows = db.execute(select(HealthDaily).where(HealthDaily.day == day)).scalars().all()
    def pick(attr):
        for r in rows:
            v = getattr(r, attr)
            if v is not None:
                return v
        return None
    return {"hrv_sdnn": pick("hrv_sdnn"), "resting_hr": pick("resting_hr"),
            "sleep_hours": pick("sleep_hours"), "respiratory_rate": pick("respiratory_rate")}


def _workout_for_window(db, start, end):
    """The Apple Watch workout overlapping a session's [start, end] window, if any."""
    if start is None or end is None:
        return {}
    w = db.execute(
        select(Workout).where(Workout.start_ts <= end, Workout.end_ts >= start)
        .order_by(desc(Workout.start_ts)).limit(1)
    ).scalar_one_or_none()
    if not w:
        return {}
    return {"insession_hr_avg": w.avg_hr, "insession_hr_max": w.max_hr,
            "active_energy": w.active_energy, "duration_min": w.duration_min}


@app.get("/api/session_points")
def session_points():
    """Per-session joined metrics for the relationship scatter plots.

    Each rated session is joined to that day's wearable recovery (sleep/HRV/RHR)
    and to any Apple Watch workout overlapping the session window (in-session HR,
    active energy). Powers the 'your real sessions' overlay on the Summary charts.
    """
    db = SessionLocal()
    try:
        sessions = db.execute(select(SessionModel).order_by(SessionModel.day)).scalars().all()
        out = []
        for s in sessions:
            if s.subjective_rating_1_10 is None:
                continue
            h = _health_for_day(db, s.day)
            w = _workout_for_window(db, s.start_ts, s.end_ts)
            out.append({
                "session_id": s.session_id, "day": s.day.isoformat(),
                "rating": s.subjective_rating_1_10,
                "sleep_hours": h.get("sleep_hours"), "hrv": h.get("hrv_sdnn"),
                "resting_hr": h.get("resting_hr"),
                "insession_hr_avg": w.get("insession_hr_avg"),
                "active_energy": w.get("active_energy"),
            })
        return {"points": out}
    finally:
        db.close()


@app.get("/api/recovery")
def recovery():
    """Latest available wearable recovery values (for the dashboard's Recovery card)."""
    db = SessionLocal()
    try:
        rows = db.execute(select(HealthDaily).order_by(desc(HealthDaily.day))).scalars().all()
        def last(attr):
            for r in rows:
                v = getattr(r, attr)
                if v is not None:
                    return {"value": round(v, 1), "day": r.day.isoformat(), "source": r.source}
            return None
        wk = db.execute(select(Workout).order_by(desc(Workout.start_ts)).limit(1)).scalar_one_or_none()
        return {
            "hrv": last("hrv_sdnn"), "resting_hr": last("resting_hr"),
            "sleep_hours": last("sleep_hours"), "respiratory_rate": last("respiratory_rate"),
            "last_workout": ({"name": wk.name, "avg_hr": wk.avg_hr, "max_hr": wk.max_hr,
                              "active_energy": wk.active_energy, "duration_min": wk.duration_min,
                              "day": wk.start_ts.date().isoformat() if wk.start_ts else None} if wk else None),
        }
    finally:
        db.close()


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


# ------------------------------------------------------------------- people API
def _ratings_for_person(db, person_id, role):
    sids = [sp.session_id for sp in db.execute(select(SessionPerson).where(
        (SessionPerson.person_id == person_id) & (SessionPerson.role == role))).scalars().all()]
    out = []
    for sid in sids:
        s = db.get(SessionModel, sid)
        if s and s.subjective_rating_1_10 is not None:
            out.append(s.subjective_rating_1_10)
    return out


def _overall_avg(db):
    rs = [s.subjective_rating_1_10 for s in db.execute(select(SessionModel)).scalars().all()
          if s.subjective_rating_1_10 is not None]
    return sum(rs) / len(rs) if rs else None


def _estimated_ability(ap, ao, overall):
    """Estimate a person's skill from how your rating moves with/against them:
    a strong partner lifts your game; a strong opponent drags it down."""
    if overall is None:
        return None
    parts = []
    if ap:
        parts.append((len(ap), 5.5 + (sum(ap) / len(ap) - overall)))
    if ao:
        parts.append((len(ao), 5.5 + (overall - sum(ao) / len(ao))))
    if not parts:
        return None
    est = sum(w * v for w, v in parts) / sum(w for w, _ in parts)
    return round(max(1.0, min(10.0, est)), 1)


def _person_summary(db, p, overall=None) -> dict:
    ap = _ratings_for_person(db, p.id, "partner")
    ao = _ratings_for_person(db, p.id, "opponent")
    if overall is None:
        overall = _overall_avg(db)
    return {"id": p.id, "name": p.name, "kind": p.kind, "color": p.color, "notes": p.notes,
            "ability_self": p.ability_self, "ability_est": _estimated_ability(ap, ao, overall),
            "n_partner": len(ap), "avg_partner": round(sum(ap) / len(ap), 2) if ap else None,
            "n_opponent": len(ao), "avg_opponent": round(sum(ao) / len(ao), 2) if ao else None}


@app.get("/api/people")
def list_people():
    db = SessionLocal()
    try:
        overall = _overall_avg(db)
        people = db.execute(select(Person).order_by(Person.name)).scalars().all()
        return [_person_summary(db, p, overall) for p in people]
    finally:
        db.close()


@app.post("/api/people")
def create_person(p: PersonIn):
    db = SessionLocal()
    try:
        if not (p.name or "").strip():
            raise HTTPException(400, "name required")
        person = _get_or_create_person(db, p.name, p.kind or "both")
        if p.kind:
            person.kind = p.kind
        if p.ability_self is not None:
            person.ability_self = p.ability_self
        if p.notes is not None:
            person.notes = p.notes
        db.commit()
        return {"ok": True, "id": person.id}
    finally:
        db.close()


@app.get("/api/people/{pid}")
def get_person(pid: str):
    db = SessionLocal()
    try:
        p = db.get(Person, pid)
        if not p:
            raise HTTPException(404, "no such person")
        sps = db.execute(select(SessionPerson).where(SessionPerson.person_id == pid)).scalars().all()
        hist = []
        for sp in sps:
            s = db.get(SessionModel, sp.session_id)
            if not s:
                continue
            hist.append({"session_id": s.session_id, "day": s.day.isoformat(), "role": sp.role,
                         "rating": s.subjective_rating_1_10, "location": s.location})
        hist.sort(key=lambda h: h["day"], reverse=True)
        d = _person_summary(db, p)
        d["history"] = hist
        return d
    finally:
        db.close()


@app.patch("/api/people/{pid}")
def patch_person(pid: str, p: PersonIn):
    db = SessionLocal()
    try:
        person = db.get(Person, pid)
        if not person:
            raise HTTPException(404, "no such person")
        if p.name and p.name.strip():
            person.name = p.name.strip()
        if p.kind:
            person.kind = p.kind
        if p.ability_self is not None:
            person.ability_self = p.ability_self
        if p.notes is not None:
            person.notes = p.notes
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@app.delete("/api/people/{pid}")
def delete_person(pid: str):
    db = SessionLocal()
    try:
        db.execute(SessionPerson.__table__.delete().where(SessionPerson.person_id == pid))
        person = db.get(Person, pid)
        if person:
            db.delete(person)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


# -------------------------------------------------------------------- map / courts
@app.get("/api/courts")
def courts():
    """Sessions grouped by court (location name, else rounded coords) for the Map tab."""
    db = SessionLocal()
    try:
        sessions = db.execute(select(SessionModel)).scalars().all()
        groups: dict[str, dict] = {}
        for s in sessions:
            if s.lat is None or s.lon is None:
                continue
            key = (s.location or "").strip().lower() or f"{round(s.lat, 3)},{round(s.lon, 3)}"
            g = groups.setdefault(key, {"name": s.location or "Unnamed court", "lats": [], "lons": [],
                                        "ratings": [], "winds": [], "sands": [], "sessions": []})
            g["lats"].append(s.lat)
            g["lons"].append(s.lon)
            if s.subjective_rating_1_10 is not None:
                g["ratings"].append(s.subjective_rating_1_10)
            agg = _aggregate(_court_window(db, s.start_ts, s.end_ts)) if s.start_ts else {}
            if agg.get("wind_sound"):
                g["winds"].append(agg["wind_sound"]["mean"])
            if agg.get("sand_temp"):
                g["sands"].append(agg["sand_temp"]["mean"])
            g["sessions"].append(s.session_id)
        avg = lambda L: round(sum(L) / len(L), 1) if L else None
        out = []
        for g in groups.values():
            pc: dict[str, int] = {}
            for sid in g["sessions"]:
                for sp in db.execute(select(SessionPerson).where(
                        (SessionPerson.session_id == sid) & (SessionPerson.role == "partner"))).scalars().all():
                    pe = db.get(Person, sp.person_id)
                    if pe:
                        pc[pe.name] = pc.get(pe.name, 0) + 1
            out.append({"name": g["name"],
                        "lat": sum(g["lats"]) / len(g["lats"]), "lon": sum(g["lons"]) / len(g["lons"]),
                        "n": len(g["sessions"]), "avg_rating": avg(g["ratings"]),
                        "avg_wind": avg(g["winds"]), "avg_sand_temp": avg(g["sands"]),
                        "partners": [{"name": k, "n": v} for k, v in sorted(pc.items(), key=lambda x: -x[1])]})
        out.sort(key=lambda c: -c["n"])
        return out
    finally:
        db.close()


# --------------------------------------------------------- relationship signals
@app.get("/api/relationships")
def relationships():
    """Flag partners/opponents your ratings move with — Welch's t, small-N guarded."""
    db = SessionLocal()
    try:
        rated = [s for s in db.execute(select(SessionModel)).scalars().all()
                 if s.subjective_rating_1_10 is not None]
        by_sid = {s.session_id: s.subjective_rating_1_10 for s in rated}
        alerts = []
        MIN_N = 3
        for p in db.execute(select(Person)).scalars().all():
            for role in ("partner", "opponent"):
                sids = {sp.session_id for sp in db.execute(select(SessionPerson).where(
                    (SessionPerson.person_id == p.id) & (SessionPerson.role == role))).scalars().all()}
                with_ = [by_sid[s] for s in sids if s in by_sid]
                without = [r for sid, r in by_sid.items() if sid not in sids]
                if len(with_) < MIN_N or len(without) < 2:
                    continue
                mw, mo = sum(with_) / len(with_), sum(without) / len(without)
                diff = mw - mo
                if abs(diff) < 0.8:
                    continue
                pval = _welch_p(with_, without)
                if pval is None or pval >= 0.1:
                    continue
                alerts.append({"person": p.name, "person_id": p.id, "role": role,
                               "kind": "boost" if diff > 0 else "drag", "n": len(with_),
                               "mean_with": round(mw, 1), "mean_other": round(mo, 1),
                               "diff": round(diff, 1), "p": round(pval, 3)})
        alerts.sort(key=lambda a: a["p"])
        return {"alerts": alerts, "n_rated": len(rated)}
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
