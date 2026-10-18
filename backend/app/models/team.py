from sqlalchemy import Column, String, Text, DateTime, func
from sqlalchemy.orm import relationship
import uuid
from app.database import Base

class Team(Base):
    __tablename__ = "teams"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    memberships = relationship("Membership", back_populates="team", cascade="all, delete-orphan")
    work_items = relationship("WorkItem", back_populates="team", cascade="all, delete-orphan")
