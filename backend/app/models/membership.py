from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import relationship
import uuid
from app.database import Base

class Membership(Base):
    __tablename__ = "memberships"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id = Column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False, default="Member")  # Viewer, Member, Lead, Admin
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "team_id", name="uq_user_team"),
    )

    user = relationship("User", back_populates="memberships")
    team = relationship("Team", back_populates="memberships")
