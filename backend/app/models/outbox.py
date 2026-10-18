from sqlalchemy import Column, String, Integer, Text, JSON, DateTime, Index, func
import uuid
from app.database import Base

class OutboxJob(Base):
    __tablename__ = "outbox_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    dedupe_key = Column(String(255), unique=True, nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="PENDING")  # PENDING, PROCESSING, COMPLETED, FAILED
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    next_run_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_outbox_status_next_run", "status", "next_run_at"),
    )
