from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index, JSON, func
from sqlalchemy.orm import relationship
import uuid
from app.database import Base

class ActivityEvent(Base):
    __tablename__ = "activity_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    work_item_id = Column(String(36), ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type = Column(String(50), nullable=False)  # created, claimed, assigned, updated, transitioned, commented
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    comment_body = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_activity_events_item_created", "work_item_id", "created_at"),
    )

    work_item = relationship("WorkItem", back_populates="activity_events")
    actor = relationship("User", back_populates="activity_events")
