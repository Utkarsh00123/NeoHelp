from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models import User, Membership
from app.core.security import verify_password, create_access_token
from app.core.dependencies import get_current_user, AuthenticatedUser
from app.schemas.auth import LoginRequest, TokenResponse, UserSummary, TeamRoleMembership
from typing import List

router = APIRouter(prefix="/auth", tags=["Authentication"])

def format_user_summary(user: User) -> UserSummary:
    memberships_list = [
        TeamRoleMembership(
            team_id=m.team_id,
            team_name=m.team.name if m.team else "Unknown",
            role=m.role
        )
        for m in user.memberships
    ]
    return UserSummary(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        memberships=memberships_list
    )

@router.post("/login", response_model=TokenResponse)
async def login(credentials: LoginRequest, db: AsyncSession = Depends(get_db)):
    query = (
        select(User)
        .options(selectinload(User.memberships).selectinload(Membership.team))
        .where(User.email == credentials.email)
    )
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = create_access_token(subject=user.id)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=format_user_summary(user)
    )

@router.get("/me", response_model=UserSummary)
async def get_me(current_user: AuthenticatedUser = Depends(get_current_user)):
    return format_user_summary(current_user.user)

@router.get("/users", response_model=List[UserSummary])
async def list_seeded_users(db: AsyncSession = Depends(get_db)):
    """List seeded demo users with team memberships for quick role-switching in development."""
    query = (
        select(User)
        .options(selectinload(User.memberships).selectinload(Membership.team))
        .order_by(User.full_name)
    )
    result = await db.execute(query)
    users = result.scalars().all()
    return [format_user_summary(u) for u in users]

@router.post("/switch/{user_id}", response_model=TokenResponse)
async def switch_user(user_id: str, db: AsyncSession = Depends(get_db)):
    """Convenience token generator for role-switching without re-entering password."""
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
            detail="User not found."
        )
    
    token = create_access_token(subject=user.id)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=format_user_summary(user)
    )
