"""Database models + engine. SQLite locally, Postgres on Render (via DATABASE_URL)."""
import os
from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Float, Integer, DateTime, Date, Text, JSON, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

# Default: local SQLite file next to the app. On Render, set DATABASE_URL to the
# managed Postgres URL. Render hands out `postgres://...`; SQLAlchemy wants
# `postgresql://...`.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./courtside.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class CourtReading(Base):
    __tablename__ = "court_readings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(64), index=True, default="court-node-1")
    server_ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    device_millis: Mapped[Optional[int]] = mapped_column(Integer)
    temp_c: Mapped[Optional[float]] = mapped_column(Float)
    humidity_pct: Mapped[Optional[float]] = mapped_column(Float)
    pressure_hpa: Mapped[Optional[float]] = mapped_column(Float)
    ir_object_c: Mapped[Optional[float]] = mapped_column(Float)
    ir_ambient_c: Mapped[Optional[float]] = mapped_column(Float)
    sound_pp: Mapped[Optional[float]] = mapped_column(Float)


class HealthDaily(Base):
    """One row per (day, source). Upserted by the health ingest / Oura backfill."""
    __tablename__ = "health_daily"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(32), default="apple")
    hrv_sdnn: Mapped[Optional[float]] = mapped_column(Float)
    resting_hr: Mapped[Optional[float]] = mapped_column(Float)
    sleep_hours: Mapped[Optional[float]] = mapped_column(Float)
    respiratory_rate: Mapped[Optional[float]] = mapped_column(Float)
    raw: Mapped[Optional[dict]] = mapped_column(JSON)  # every metric HAE sent (lossless)


class Session(Base):
    __tablename__ = "sessions"
    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    start_ts: Mapped[Optional[datetime]] = mapped_column(DateTime)
    end_ts: Mapped[Optional[datetime]] = mapped_column(DateTime)
    location: Mapped[Optional[str]] = mapped_column(String(128))
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lon: Mapped[Optional[float]] = mapped_column(Float)
    partner: Mapped[Optional[str]] = mapped_column(String(128))
    opponent_level: Mapped[Optional[str]] = mapped_column(String(64))
    subjective_rating_1_10: Mapped[Optional[float]] = mapped_column(Float)
    peer_rating_1_10: Mapped[Optional[float]] = mapped_column(Float)    # teammate eval (ground truth)
    coach_rating_1_10: Mapped[Optional[float]] = mapped_column(Float)   # coach eval (ground truth)
    wind_self_report: Mapped[Optional[int]] = mapped_column(Integer)  # 0=calm .. 5=strong
    energy_1_5: Mapped[Optional[int]] = mapped_column(Integer)      # player state (survey-driven)
    soreness_1_5: Mapped[Optional[int]] = mapped_column(Integer)
    mental_1_5: Mapped[Optional[int]] = mapped_column(Integer)
    warmup_1_5: Mapped[Optional[int]] = mapped_column(Integer)
    food_timing: Mapped[Optional[str]] = mapped_column(String(64))
    felt_state: Mapped[Optional[str]] = mapped_column(Text)
    kills: Mapped[Optional[int]] = mapped_column(Integer)
    errors: Mapped[Optional[int]] = mapped_column(Integer)
    sets_won: Mapped[Optional[int]] = mapped_column(Integer)
    sets_lost: Mapped[Optional[int]] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="done")  # "recording" | "done"


class Workout(Base):
    """Apple Watch workouts (in-session intensity + cross-training load)."""
    __tablename__ = "workouts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(64))      # e.g. "Volleyball", "Running"
    start_ts: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    end_ts: Mapped[Optional[datetime]] = mapped_column(DateTime)
    duration_min: Mapped[Optional[float]] = mapped_column(Float)
    active_energy: Mapped[Optional[float]] = mapped_column(Float)  # kcal
    avg_hr: Mapped[Optional[float]] = mapped_column(Float)
    max_hr: Mapped[Optional[float]] = mapped_column(Float)
    distance_m: Mapped[Optional[float]] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32), default="apple")
    raw: Mapped[Optional[dict]] = mapped_column(JSON)             # full workout (lossless)


class Person(Base):
    """A real person you play with/against — partners and opponents as first-class
    records so relationships accrue history (beach volleyball is a pairing sport)."""
    __tablename__ = "people"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)        # slug of name
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(16), default="both")        # partner|opponent|both
    color: Mapped[Optional[str]] = mapped_column(String(16))             # avatar/marker color
    ability_self: Mapped[Optional[int]] = mapped_column(Integer)         # your 1-10 read on their skill
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class SessionPerson(Base):
    """Links a session to the people in it, with their role that session."""
    __tablename__ = "session_people"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    person_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(16))                        # partner|opponent


def ensure_columns():
    """Lightweight auto-migration: ADD COLUMN for any model column missing from an
    existing table (create_all only creates missing *tables*). Postgres + SQLite."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name not in existing:
                coltype = col.type.compile(dialect=engine.dialect)
                with engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {coltype}'))
