from pydantic import BaseModel
from typing import List, Optional

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserSummary"

class TeamRoleMembership(BaseModel):
    team_id: str
    team_name: str
    role: str  # Viewer, Member, Lead, Admin

class UserSummary(BaseModel):
    id: str
    email: str
    full_name: str
    memberships: List[TeamRoleMembership]

TokenResponse.model_rebuild()
