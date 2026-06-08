"""Pydantic request bodies."""
from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel


class CourtIn(BaseModel):
    node_id: Optional[str] = "court-node-1"
    device_millis: Optional[int] = None
    temp_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    pressure_hpa: Optional[float] = None
    ir_object_c: Optional[float] = None
    ir_ambient_c: Optional[float] = None
    sound_pp: Optional[float] = None


class SessionIn(BaseModel):
    session_id: Optional[str] = None
    day: Optional[date] = None
    start_ts: Optional[datetime] = None
    end_ts: Optional[datetime] = None
    location: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    partner: Optional[str] = None
    opponent_level: Optional[str] = None
    subjective_rating_1_10: Optional[float] = None
    peer_rating_1_10: Optional[float] = None
    coach_rating_1_10: Optional[float] = None
    wind_self_report: Optional[int] = None
    energy_1_5: Optional[int] = None
    soreness_1_5: Optional[int] = None
    mental_1_5: Optional[int] = None
    warmup_1_5: Optional[int] = None
    food_timing: Optional[str] = None
    felt_state: Optional[str] = None
    kills: Optional[int] = None
    errors: Optional[int] = None
    sets_won: Optional[int] = None
    sets_lost: Optional[int] = None
    notes: Optional[str] = None
    status: Optional[str] = None
