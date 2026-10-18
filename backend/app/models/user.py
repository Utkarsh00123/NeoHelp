from sqlalchemy import Column, String, DateTime, func
from sqlalchemy.orm import relationship
import uuid
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    memberships = relationship("Membership", back_populates="user", cascade="all, delete-orphan")
    assigned_items = relationship("WorkItem", back_populates="assignee", foreign_keys="WorkItem.assignee_id")
    created_items = relationship("WorkItem", back_populates="creator", foreign_keys="WorkItem.created_by_id")
    activity_events = relationship("ActivityEvent", back_populates="actor")
