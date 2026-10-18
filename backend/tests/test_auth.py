import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from app.main import app
from app.config import settings
from app.models import User, Team, Membership
from app.core.dependencies import AuthenticatedUser, ROLE_LEVELS

@pytest.mark.asyncio
async def test_auth_login_success():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/auth/login",
            json={"email": "admin@neohelp.io", "password": "password123"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == "admin@neohelp.io"
        assert len(data["user"]["memberships"]) >= 1

@pytest.mark.asyncio
async def test_auth_login_invalid_password():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/auth/login",
            json={"email": "admin@neohelp.io", "password": "wrongpassword!"}
        )
        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]

@pytest.mark.asyncio
async def test_auth_get_me_protected():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Without token
        res_no_token = await client.get("/api/auth/me")
        assert res_no_token.status_code == 401

        # With invalid token
        res_bad_token = await client.get("/api/auth/me", headers={"Authorization": "Bearer badtoken.123.456"})
        assert res_bad_token.status_code == 401

        # With valid token
        login_res = await client.post(
            "/api/auth/login",
            json={"email": "lead.incident@neohelp.io", "password": "password123"}
        )
        token = login_res.json()["access_token"]
        res_me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res_me.status_code == 200
        assert res_me.json()["email"] == "lead.incident@neohelp.io"
        assert res_me.json()["full_name"] == "Diana Prince"

@pytest.mark.asyncio
async def test_auth_list_users_and_switch():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # List users
        users_res = await client.get("/api/auth/users")
        assert users_res.status_code == 200
        users = users_res.json()
        assert len(users) >= 10

        # Switch to first user
        target_user = users[0]
        switch_res = await client.post(f"/api/auth/switch/{target_user['id']}")
        assert switch_res.status_code == 200
        data = switch_res.json()
        assert data["user"]["id"] == target_user["id"]
        assert "access_token" in data

@pytest.mark.asyncio
async def test_resource_level_rbac_logic():
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    async with session_factory() as session:
        # Fetch Bob Smith (Lead in Core Ops, Member in Incident Response)
        bob_res = await session.execute(
            select(User).where(User.email == "lead.core@neohelp.io")
        )
        bob = bob_res.scalar_one()
        bob_mems = (await session.execute(
            select(Membership).options(selectinload(Membership.team)).where(Membership.user_id == bob.id)
        )).scalars().all()
        bob_auth = AuthenticatedUser(bob, bob_mems)

        # Fetch teams
        core_team = (await session.execute(
            select(Team).where(Team.name == "Core Infrastructure & Ops")
        )).scalar_one()
        incident_team = (await session.execute(
            select(Team).where(Team.name == "Incident Response")
        )).scalar_one()
        payments_team = (await session.execute(
            select(Team).where(Team.name == "Payments & Billing Ops")
        )).scalar_one()

        # Bob in Core Ops -> Lead
        assert bob_auth.has_team_access(core_team.id) is True
        assert bob_auth.can_mutate(core_team.id) is True
        assert bob_auth.can_lead(core_team.id) is True

        # Bob in Incident Response -> Member
        assert bob_auth.has_team_access(incident_team.id) is True
        assert bob_auth.can_mutate(incident_team.id) is True
        assert bob_auth.can_lead(incident_team.id) is False  # Cannot approve as Member

        # Bob in Payments Team -> Not a member (Cross-team isolation)
        assert bob_auth.has_team_access(payments_team.id) is False
        assert bob_auth.can_mutate(payments_team.id) is False
        assert bob_auth.can_lead(payments_team.id) is False

        # Fetch Julia Roberts (Viewer in all teams)
        julia_res = await session.execute(
            select(User).where(User.email == "viewer.global@neohelp.io")
        )
        julia = julia_res.scalar_one()
        julia_mems = (await session.execute(
            select(Membership).options(selectinload(Membership.team)).where(Membership.user_id == julia.id)
        )).scalars().all()
        julia_auth = AuthenticatedUser(julia, julia_mems)

        # Viewer can read but NEVER mutate or lead
        assert julia_auth.has_team_access(core_team.id) is True
        assert julia_auth.can_mutate(core_team.id) is False  # Viewer cannot mutate
        assert julia_auth.can_lead(core_team.id) is False

    await engine.dispose()
