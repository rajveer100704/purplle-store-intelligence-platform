"""
db/models.py – SQLAlchemy ORM table definitions.

Tables:
  events            – All ingested events (primary event store)
  pos_transactions  – POS rows from CSV (for conversion correlation)
  anomaly_log       – Historical anomaly records
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, Integer, JSON, String, Text, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class EventORM(Base):
    __tablename__ = "events"

    # Primary key – event_id ensures idempotency
    event_id: Mapped[str] = mapped_column(String, primary_key=True, index=True)

    # Core fields (required by challenge schema)
    store_id: Mapped[str] = mapped_column(String, index=True)
    camera_id: Mapped[str] = mapped_column(String)
    visitor_id: Mapped[str] = mapped_column(String, index=True)
    event_type: Mapped[str] = mapped_column(String, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    # Optional fields
    zone_id: Mapped[str | None] = mapped_column(String, nullable=True)
    dwell_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False)
    session_seq: Mapped[int] = mapped_column(Integer, default=1)
    uncertain_reid: Mapped[bool] = mapped_column(Boolean, default=False)

    # Flexible metadata blob
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    # Ingestion bookkeeping
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )


class POSTransactionORM(Base):
    __tablename__ = "pos_transactions"

    txn_id: Mapped[str] = mapped_column(String, primary_key=True)
    store_id: Mapped[str] = mapped_column(String, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    visitor_id: Mapped[str | None] = mapped_column(String, nullable=True)  # after correlation
    matched: Mapped[bool] = mapped_column(Boolean, default=False)


class AnomalyLogORM(Base):
    __tablename__ = "anomaly_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[str] = mapped_column(String, index=True)
    anomaly_type: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    action: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, index=True
    )
