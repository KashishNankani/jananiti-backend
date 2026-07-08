"""
database.py
SQLite setup via SQLAlchemy (sync engine, used from FastAPI routes directly —
simple enough for a hackathon prototype, no async session complexity needed).
"""

import json
import os
from datetime import datetime, timezone

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

DB_PATH = os.path.join(os.path.dirname(__file__), "jananiti.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def now_utc():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# MODELS
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)  # plain text for demo purposes only
    role = Column(String, nullable=False)  # mp | citizen
    constituency = Column(String, nullable=True)
    created_at = Column(DateTime, default=now_utc)


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    citizen_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    timestamp = Column(DateTime, default=now_utc)
    source_channel = Column(String, nullable=False)  # text|voice|image|ivrs|whatsapp|sms
    raw_content = Column(Text, nullable=True)
    transcribed_text = Column(Text, nullable=True)
    english_translation = Column(Text, nullable=True)
    detected_language = Column(String, nullable=True)
    category = Column(String, nullable=True)
    subcategory = Column(String, nullable=True)
    specific_need = Column(Text, nullable=True)
    urgency_level = Column(String, nullable=True)  # low|medium|high|critical
    sentiment = Column(String, nullable=True)  # neutral|frustrated|hopeful|desperate
    affected_population = Column(String, nullable=True)  # small|medium|large
    location_mentioned = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    keywords = Column(Text, nullable=True)  # JSON string
    image_description = Column(Text, nullable=True)
    status = Column(String, default="received")  # received|under_review|actioned|resolved
    budget_released = Column(Boolean, default=False)
    budget_amount = Column(Float, nullable=True)
    resolution_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_utc)

    def to_dict(self):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        for k in ("timestamp", "created_at"):
            if d.get(k) is not None:
                d[k] = d[k].isoformat()
        if d.get("keywords"):
            try:
                d["keywords"] = json.loads(d["keywords"])
            except Exception:
                d["keywords"] = []
        else:
            d["keywords"] = []
        return d


class Block(Base):
    __tablename__ = "blocks"

    id = Column(Integer, primary_key=True, index=True)
    block_name = Column(String, unique=True, nullable=False)
    profile = Column(String, nullable=True)
    population = Column(Integer, nullable=True)
    children_6_14 = Column(Integer, nullable=True)
    sc_st_percent = Column(Float, nullable=True)
    bpl_households = Column(Integer, nullable=True)
    nearest_school_km = Column(Float, nullable=True)
    school_capacity_used = Column(Float, nullable=True)
    nearest_hospital_km = Column(Float, nullable=True)
    hospital_capacity_used = Column(Float, nullable=True)
    road_paved_percent = Column(Float, nullable=True)
    existing_plans = Column(Text, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class Ranking(Base):
    __tablename__ = "rankings"

    id = Column(Integer, primary_key=True, index=True)
    generated_at = Column(DateTime, default=now_utc)
    priority_rank = Column(Integer, nullable=True)
    development_work = Column(Text, nullable=True)
    category = Column(String, nullable=True)
    justification = Column(Text, nullable=True)
    citizen_demand_evidence = Column(Text, nullable=True)
    estimated_beneficiaries = Column(Text, nullable=True)
    suggested_action = Column(Text, nullable=True)
    funding_source = Column(String, nullable=True)
    urgency_score = Column(Float, nullable=True)
    demand_score = Column(Float, nullable=True)
    data_alignment_score = Column(Float, nullable=True)
    equity_score = Column(Float, nullable=True)
    cascading_impact_score = Column(Float, nullable=True)
    drfi_score = Column(Float, nullable=True)
    counter_narrative_flag = Column(Boolean, default=False)
    counter_narrative_note = Column(Text, nullable=True)
    silent_need_flag = Column(Boolean, default=False)
    silent_need_note = Column(Text, nullable=True)

    def to_dict(self):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        if d.get("generated_at") is not None:
            d["generated_at"] = d["generated_at"].isoformat()
        return d


class IVRSSession(Base):
    __tablename__ = "ivrs_sessions"

    id = Column(Integer, primary_key=True, index=True)
    citizen_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    phone_number = Column(String, nullable=True)
    started_at = Column(DateTime, default=now_utc)
    completed_at = Column(DateTime, nullable=True)
    selected_category = Column(String, nullable=True)
    recorded_text = Column(Text, nullable=True)
    status = Column(String, default="completed")

    def to_dict(self):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        for k in ("started_at", "completed_at"):
            if d.get(k) is not None:
                d[k] = d[k].isoformat()
        return d


# ---------------------------------------------------------------------------
# INIT / SESSION HELPERS
# ---------------------------------------------------------------------------

def init_database():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session() -> Session:
    """For use outside FastAPI's Depends (e.g. seed_data, drfi_engine)."""
    return SessionLocal()
