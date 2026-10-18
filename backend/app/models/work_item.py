from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import relationship
import uuid
from app.database import Base

class WorkItem(Base):
    __tablename__ = "work_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    type = Column(String(50), nullable=False, default="task")  # incident, customer_issue, payment, compliance, task
    priority = Column(String(20), nullable=False, default="medium")  # low, medium, high, urgent
    status = Column(String(50), nullable=False, default="Open")  # Open, In Progress, Awaiting Approval, Resolved, Closed
    team_id = Column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    assignee_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_work_items_team_status_priority_id", "team_id", "status", "priority", "id"),
        Index("ix_work_items_created_at", "created_at"),
    )

    team = relationship("Team", back_populates="work_items")
    assignee = relationship("User", foreign_keys=[assignee_id], back_populates="assigned_items")
    creator = relationship("User", foreign_keys=[created_by_id], back_populates="created_items")
    activity_events = relationship(
        "ActivityEvent", 
        back_populates="work_item", 
        cascade="all, delete-orphan",
        order_by="ActivityEvent.created_at.desc()"
    )
