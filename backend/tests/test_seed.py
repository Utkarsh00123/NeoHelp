import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from app.config import settings
from app.models import User, Team, Membership, WorkItem, ActivityEvent
from app.core.security import verify_password

@pytest.mark.asyncio
async def test_seed_integrity():
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    async with session_factory() as session:
        # Check teams count
        teams_count = (await session.execute(select(func.count(Team.id)))).scalar()
        assert teams_count == 4

        # Check users count
        users_count = (await session.execute(select(func.count(User.id)))).scalar()
        assert users_count == 10

        # Check memberships count
        memberships_count = (await session.execute(select(func.count(Membership.id)))).scalar()
        assert memberships_count == 16

        # Check work items count
        items_count = (await session.execute(select(func.count(WorkItem.id)))).scalar()
        assert items_count >= 2500

        # Check activity events count
        events_count = (await session.execute(select(func.count(ActivityEvent.id)))).scalar()
        assert events_count >= 2500

        # Verify Alice Johnson's password verification
        user_res = await session.execute(select(User).where(User.email == "admin@neohelp.io"))
        alice = user_res.scalar_one_or_none()
        assert alice is not None
        assert verify_password("password123", alice.password_hash) is True
        assert verify_password("wrongpassword", alice.password_hash) is False

    await engine.dispose()

@pytest.mark.asyncio
async def test_work_items_concurrency_and_immutability():
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    async with session_factory() as session:
        # Grab 10 sample items
        res = await session.execute(select(WorkItem).limit(10))
        items = res.scalars().all()
        assert len(items) == 10
        for item in items:
            assert item.version >= 1
            # Check associated activity event
            event_res = await session.execute(
                select(ActivityEvent).where(ActivityEvent.work_item_id == item.id)
            )
            events = event_res.scalars().all()
            assert len(events) >= 1
            # At least one created event
            event_types = [e.event_type for e in events]
            assert "created" in event_types

    await engine.dispose()
