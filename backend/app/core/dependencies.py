from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from jose import jwt, JWTError
from typing import Optional, List, Dict
from app.database import get_db
from app.config import settings
from app.models import User, Membership, Team

security_scheme = HTTPBearer(auto_error=False)

ROLE_LEVELS = {
    "Viewer": 1,
    "Member": 2,
    "Lead": 3,
    "Admin": 4,
}

class AuthenticatedUser:
    def __init__(self, user: User, memberships: List[Membership]):
        self.user = user
        self.id = user.id
        self.email = user.email
        self.full_name = user.full_name
        self.memberships = memberships
        # Map: team_id -> role
        self.team_roles: Dict[str, str] = {m.team_id: m.role for m in memberships}
        # Map: team_name -> role
        self.team_name_roles: Dict[str, str] = {
            m.team.name: m.role for m in memberships if "team" in m.__dict__ and m.team is not None
        }
        self.team_ids: List[str] = list(self.team_roles.keys())

    def get_role_in_team(self, team_id: str) -> Optional[str]:
        return self.team_roles.get(team_id)

    def has_team_access(self, team_id: str, min_role: Optional[str] = None) -> bool:
        user_role = self.get_role_in_team(team_id)
        if not user_role:
            return False
        if not min_role:
            return True
        return ROLE_LEVELS.get(user_role, 0) >= ROLE_LEVELS.get(min_role, 0)

    def can_mutate(self, team_id: str) -> bool:
        """Viewers are read-only; mutation requires at least Member role."""
        return self.has_team_access(team_id, min_role="Member")

    def can_lead(self, team_id: str) -> bool:
        """Requires Lead or Admin role in the team."""
        return self.has_team_access(team_id, min_role="Lead")

    def is_admin(self) -> bool:
        """Return whether the user has an Admin membership in any team."""
        return any(role == "Admin" for role in self.team_roles.values())


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: AsyncSession = Depends(get_db)
) -> AuthenticatedUser:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials missing.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload.",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch user with loaded memberships and teams
    query = (
        select(User)
        .options(selectinload(User.memberships).selectinload(Membership.team))
        .where(User.id == user_id)
    )
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authenticated user no longer exists."
        )

    return AuthenticatedUser(user=user, memberships=user.memberships)


def require_team_role(min_role: Optional[str] = None):
    """
    Dependency factory to enforce team membership and role checks on endpoints.
    Accepts team_id from request path or query parameters.
    """
    async def dependency(
        team_id: str,
        current_user: AuthenticatedUser = Depends(get_current_user)
    ) -> AuthenticatedUser:
        user_role = current_user.get_role_in_team(team_id)
        if not user_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You do not have access to this team's resources."
            )
        
        if min_role and ROLE_LEVELS.get(user_role, 0) < ROLE_LEVELS.get(min_role, 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Action requires at least '{min_role}' role (current: '{user_role}')."
            )
        return current_user

    return dependency
