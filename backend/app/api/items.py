from fastapi import APIRouter, Depends, HTTPException, status, Header, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, or_, and_, desc, func
from sqlalchemy.orm import selectinload
from typing import Optional, List
import uuid
import json
from datetime import datetime, timezone

from app.database import get_db
from app.models import WorkItem, ActivityEvent, OutboxJob, Team, User
from app.core.dependencies import get_current_user, AuthenticatedUser
from app.core.idempotency import check_idempotency, store_idempotency
from app.schemas.work_item import (
    WorkItemCreate,
    WorkItemUpdate,
    WorkItemTransition,
    CommentCreate,
    WorkItemResponse,
    ActivityEventResponse,
    PaginatedWorkItems
)

router = APIRouter(prefix="/items", tags=["Work Items"])

VALID_TRANSITIONS = {
    "Open": ["In Progress"],
    "In Progress": ["Open", "Awaiting Approval"],
    "Awaiting Approval": ["In Progress", "Resolved"],
    "Resolved": ["Closed", "In Progress"],
    "Closed": []
}

def serialize_item(item: WorkItem) -> WorkItemResponse:
    return WorkItemResponse(
        id=item.id,
        title=item.title,
        description=item.description,
        type=item.type,
        priority=item.priority,
        status=item.status,
        team_id=item.team_id,
        team_name=item.team.name if item.team else None,
        assignee_id=item.assignee_id,
        assignee_name=item.assignee.full_name if item.assignee else None,
        created_by_id=item.created_by_id,
        creator_name=item.creator.full_name if item.creator else None,
        due_date=item.due_date,
        version=item.version,
        created_at=item.created_at,
        updated_at=item.updated_at
    )

def serialize_activity(event: ActivityEvent) -> ActivityEventResponse:
    return ActivityEventResponse(
        id=event.id,
        work_item_id=event.work_item_id,
        actor_id=event.actor_id,
        actor_name=event.actor.full_name if event.actor else "System",
        event_type=event.event_type,
        old_value=event.old_value,
        new_value=event.new_value,
        comment_body=event.comment_body,
        created_at=event.created_at
    )

@router.get("", response_model=PaginatedWorkItems)
async def list_work_items(
    team_id: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assigned_to_me: bool = False,
    unassigned_urgent: bool = False,
    awaiting_approval: bool = False,
    q: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=50),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Enforce team scoping
    if team_id:
        if not current_user.has_team_access(team_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You do not have access to this team's work items."
            )
        team_scope = [team_id]
    else:
        team_scope = current_user.team_ids

    if not team_scope:
        return PaginatedWorkItems(items=[], next_cursor=None, has_more=False, total_count=0)

    query = (
        select(WorkItem)
        .options(
            selectinload(WorkItem.team),
            selectinload(WorkItem.assignee),
            selectinload(WorkItem.creator)
        )
        .where(WorkItem.team_id.in_(team_scope))
    )

    # Queue filters
    if assigned_to_me:
        query = query.where(WorkItem.assignee_id == current_user.id)
    if unassigned_urgent:
        query = query.where(
            and_(
                WorkItem.assignee_id.is_(None),
                WorkItem.priority.in_(["high", "urgent"]),
                WorkItem.status.in_(["Open", "In Progress"])
            )
        )
    if awaiting_approval:
        query = query.where(WorkItem.status == "Awaiting Approval")

    if status:
        query = query.where(WorkItem.status == status)
    if priority:
        query = query.where(WorkItem.priority == priority)
    if q:
        query = query.where(WorkItem.title.ilike(f"%{q}%"))

    # Cursor Pagination (based on created_at timestamp and id)
    if cursor:
        try:
            cursor_ts_str, cursor_id = cursor.split("__", 1)
            cursor_dt = datetime.fromtimestamp(float(cursor_ts_str), tz=timezone.utc)
            query = query.where(
                or_(
                    WorkItem.created_at < cursor_dt,
                    and_(WorkItem.created_at == cursor_dt, WorkItem.id < cursor_id)
                )
            )
        except Exception as e:
            print(f"Cursor parsing warning: {e}")

    query = query.order_by(desc(WorkItem.created_at), desc(WorkItem.id)).limit(limit + 1)
    result = await db.execute(query)
    items = result.scalars().all()

    has_more = len(items) > limit
    paginated_slice = items[:limit]

    next_cursor = None
    if has_more and paginated_slice:
        last_item = paginated_slice[-1]
        next_cursor = f"{last_item.created_at.timestamp()}__{last_item.id}"

    return PaginatedWorkItems(
        items=[serialize_item(item) for item in paginated_slice],
        next_cursor=next_cursor,
        has_more=has_more
    )

@router.post("", response_model=WorkItemResponse, status_code=status.HTTP_201_CREATED)
async def create_work_item(
    payload: WorkItemCreate,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Idempotency check
    stored = await check_idempotency(db, idempotency_key, current_user.id, "/api/items", payload.model_dump())
    if stored:
        status_code, body = stored
        return Response(content=json.dumps(body), status_code=status_code, media_type="application/json")

    # RBAC check: must be member of team with mutation permissions
    if not current_user.has_team_access(payload.team_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You cannot create items for a team you do not belong to."
        )
    if not current_user.can_mutate(payload.team_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Viewer role cannot create work items."
        )

    now = datetime.now(timezone.utc)
    item_id = str(uuid.uuid4())
    work_item = WorkItem(
        id=item_id,
        title=payload.title,
        description=payload.description,
        type=payload.type,
        priority=payload.priority,
        status="Open",
        team_id=payload.team_id,
        assignee_id=None,
        created_by_id=current_user.id,
        due_date=payload.due_date,
        version=1,
        created_at=now,
        updated_at=now
    )
    db.add(work_item)

    # Atomic Dual-Write 1: Activity Event
    event = ActivityEvent(
        id=str(uuid.uuid4()),
        work_item_id=item_id,
        actor_id=current_user.id,
        event_type="created",
        old_value=None,
        new_value={"title": payload.title, "priority": payload.priority, "status": "Open"},
        comment_body=f"Work item created by {current_user.full_name}.",
        created_at=now
    )
    db.add(event)

    # Atomic Dual-Write 2: Transactional Outbox Job
    outbox = OutboxJob(
        id=str(uuid.uuid4()),
        dedupe_key=f"item-created-{item_id}",
        payload={"event": "item_created", "item_id": item_id, "team_id": payload.team_id, "title": payload.title},
        status="PENDING",
        attempts=0,
        max_attempts=3,
        next_run_at=now
    )
    db.add(outbox)

    await db.flush()
    # Eager load relationships for response
    await db.refresh(work_item, ["team", "assignee", "creator"])
    response_data = serialize_item(work_item).model_dump(mode="json")

    # Store idempotency record
    await store_idempotency(
        db,
        idempotency_key,
        current_user.id,
        "/api/items",
        payload.model_dump(),
        status.HTTP_201_CREATED,
        response_data
    )

    await db.commit()
    return serialize_item(work_item)

@router.get("/{id}", response_model=WorkItemResponse)
async def get_work_item(
    id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = (
        select(WorkItem)
        .options(
            selectinload(WorkItem.team),
            selectinload(WorkItem.assignee),
            selectinload(WorkItem.creator)
        )
        .where(WorkItem.id == id)
    )
    result = await db.execute(query)
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work item not found.")

    if not current_user.has_team_access(item.team_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have access to this team's work items."
        )

    return serialize_item(item)

@router.post("/{id}/claim", response_model=WorkItemResponse)
async def claim_work_item(
    id: str,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Idempotency check
    stored = await check_idempotency(db, idempotency_key, current_user.id, f"/api/items/{id}/claim", {})
    if stored:
        status_code, body = stored
        return Response(content=json.dumps(body), status_code=status_code, media_type="application/json")

    # First fetch item to check existence and RBAC
    item = (await db.execute(select(WorkItem).where(WorkItem.id == id))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work item not found.")

    if not current_user.has_team_access(item.team_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You are not a member of this team."
        )
    if not current_user.can_mutate(item.team_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Viewer role cannot claim work items."
        )

    now = datetime.now(timezone.utc)

    # CRITICAL BEHAVIOR 2: Conditional Update for Concurrent Claims
    stmt = (
        update(WorkItem)
        .where(and_(WorkItem.id == id, WorkItem.assignee_id.is_(None)))
        .values(
            assignee_id=current_user.id,
            version=WorkItem.version + 1,
            updated_at=now
        )
    )
    res = await db.execute(stmt)
    if res.rowcount == 0:
        # Zero rows updated -> someone claimed it concurrently!
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflict: This item has already been claimed by another operator."
        )

    # In exact same transaction: write ActivityEvent
    event = ActivityEvent(
        id=str(uuid.uuid4()),
        work_item_id=id,
        actor_id=current_user.id,
        event_type="claimed",
        old_value={"assignee_id": None},
        new_value={"assignee_id": current_user.id},
        comment_body=f"Item claimed by {current_user.full_name}.",
        created_at=now
    )
    db.add(event)

    # In exact same transaction: write OutboxJob
    outbox = OutboxJob(
        id=str(uuid.uuid4()),
        dedupe_key=f"item-claimed-{id}-{current_user.id}-{int(now.timestamp())}",
        payload={"event": "item_claimed", "item_id": id, "assignee_id": current_user.id},
        status="PENDING",
        attempts=0,
        max_attempts=3,
        next_run_at=now
    )
    db.add(outbox)

    # Refetch item
    refreshed_item = (
        await db.execute(
            select(WorkItem)
            .options(
                selectinload(WorkItem.team),
                selectinload(WorkItem.assignee),
                selectinload(WorkItem.creator)
            )
            .where(WorkItem.id == id)
        )
    ).scalar_one()

    response_data = serialize_item(refreshed_item).model_dump(mode="json")
    await store_idempotency(db, idempotency_key, current_user.id, f"/api/items/{id}/claim", {}, status.HTTP_200_OK, response_data)

    await db.commit()
    return serialize_item(refreshed_item)

@router.patch("/{id}", response_model=WorkItemResponse)
async def update_work_item(
    id: str,
    payload: WorkItemUpdate,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Idempotency check
    stored = await check_idempotency(db, idempotency_key, current_user.id, f"/api/items/{id}", payload.model_dump())
    if stored:
        status_code, body = stored
        return Response(content=json.dumps(body), status_code=status_code, media_type="application/json")

    item = (await db.execute(select(WorkItem).where(WorkItem.id == id))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work item not found.")

    if not current_user.has_team_access(item.team_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: You are not in this team.")
    if not current_user.can_mutate(item.team_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: Viewer cannot edit items.")

    now = datetime.now(timezone.utc)
    old_values = {}
    update_vals = {
        "version": WorkItem.version + 1,
        "updated_at": now
    }

    if payload.title is not None:
        old_values["title"] = item.title
        update_vals["title"] = payload.title
    if payload.description is not None:
        old_values["description"] = item.description
        update_vals["description"] = payload.description
    if payload.priority is not None:
        old_values["priority"] = item.priority
        update_vals["priority"] = payload.priority
    if payload.due_date is not None:
        old_values["due_date"] = str(item.due_date)
        update_vals["due_date"] = payload.due_date

    # CRITICAL BEHAVIOR 3: Optimistic Locking with Version Check
    stmt = (
        update(WorkItem)
        .where(and_(WorkItem.id == id, WorkItem.version == payload.version))
        .values(**update_vals)
    )
    res = await db.execute(stmt)
    if res.rowcount == 0:
        await db.rollback()
        # Fetch current server version for user reconciliation
        latest_item = (
            await db.execute(
                select(WorkItem)
                .options(selectinload(WorkItem.team), selectinload(WorkItem.assignee), selectinload(WorkItem.creator))
                .where(WorkItem.id == id)
            )
        ).scalar_one()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Conflict: This work item was modified by another operator. Please reload.",
                "server_version": latest_item.version,
                "current_item": serialize_item(latest_item).model_dump(mode="json")
            }
        )

    # In exact same transaction: write ActivityEvent
    event = ActivityEvent(
        id=str(uuid.uuid4()),
        work_item_id=id,
        actor_id=current_user.id,
        event_type="updated",
        old_value=old_values,
        new_value={k: v for k, v in update_vals.items() if k not in ["version", "updated_at"]},
        comment_body=f"Item updated (v{payload.version} -> v{payload.version + 1}) by {current_user.full_name}.",
        created_at=now
    )
    db.add(event)

    refreshed_item = (
        await db.execute(
            select(WorkItem)
            .options(selectinload(WorkItem.team), selectinload(WorkItem.assignee), selectinload(WorkItem.creator))
            .where(WorkItem.id == id)
        )
    ).scalar_one()

    response_data = serialize_item(refreshed_item).model_dump(mode="json")
    await store_idempotency(db, idempotency_key, current_user.id, f"/api/items/{id}", payload.model_dump(), status.HTTP_200_OK, response_data)

    await db.commit()
    return serialize_item(refreshed_item)

@router.post("/{id}/transition", response_model=WorkItemResponse)
async def transition_work_item(
    id: str,
    payload: WorkItemTransition,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Idempotency check
    stored = await check_idempotency(db, idempotency_key, current_user.id, f"/api/items/{id}/transition", payload.model_dump())
    if stored:
        status_code, body = stored
        return Response(content=json.dumps(body), status_code=status_code, media_type="application/json")

    item = (await db.execute(select(WorkItem).where(WorkItem.id == id))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work item not found.")

    if not current_user.has_team_access(item.team_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: You are not in this team.")
    if not current_user.can_mutate(item.team_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: Viewer cannot change state.")

    # CRITICAL BEHAVIOR 4: Workflow Rules & Approval Gate
    allowed = VALID_TRANSITIONS.get(item.status, [])
    if payload.target_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid transition from '{item.status}' to '{payload.target_status}'. Allowed: {allowed}."
        )

    # Lead role required for advancing to Resolved or Closed
    if payload.target_status in ["Resolved", "Closed"]:
        if not current_user.can_lead(item.team_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Advancing an item to '{payload.target_status}' requires a Lead or Admin role for this team."
            )

    now = datetime.now(timezone.utc)
    old_status = item.status

    stmt = (
        update(WorkItem)
        .where(WorkItem.id == id)
        .values(
            status=payload.target_status,
            version=WorkItem.version + 1,
            updated_at=now
        )
    )
    await db.execute(stmt)

    # In exact same transaction: write ActivityEvent
    event = ActivityEvent(
        id=str(uuid.uuid4()),
        work_item_id=id,
        actor_id=current_user.id,
        event_type="transitioned",
        old_value={"status": old_status},
        new_value={"status": payload.target_status},
        comment_body=payload.comment or f"State transitioned from {old_status} to {payload.target_status}.",
        created_at=now
    )
    db.add(event)

    # In exact same transaction: write OutboxJob
    outbox = OutboxJob(
        id=str(uuid.uuid4()),
        dedupe_key=f"item-trans-{id}-{payload.target_status}-{int(now.timestamp())}",
        payload={"event": "item_transitioned", "item_id": id, "from": old_status, "to": payload.target_status},
        status="PENDING",
        attempts=0,
        max_attempts=3,
        next_run_at=now
    )
    db.add(outbox)

    refreshed_item = (
        await db.execute(
            select(WorkItem)
            .options(selectinload(WorkItem.team), selectinload(WorkItem.assignee), selectinload(WorkItem.creator))
            .where(WorkItem.id == id)
        )
    ).scalar_one()

    response_data = serialize_item(refreshed_item).model_dump(mode="json")
    await store_idempotency(db, idempotency_key, current_user.id, f"/api/items/{id}/transition", payload.model_dump(), status.HTTP_200_OK, response_data)

    await db.commit()
    return serialize_item(refreshed_item)

@router.get("/{id}/activity", response_model=List[ActivityEventResponse])
async def get_item_activity_timeline(
    id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    item = (await db.execute(select(WorkItem).where(WorkItem.id == id))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work item not found.")

    if not current_user.has_team_access(item.team_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: You are not in this team.")

    query = (
        select(ActivityEvent)
        .options(selectinload(ActivityEvent.actor))
        .where(ActivityEvent.work_item_id == id)
        .order_by(desc(ActivityEvent.created_at))
    )
    result = await db.execute(query)
    events = result.scalars().all()
    return [serialize_activity(e) for e in events]

@router.post("/{id}/comments", response_model=ActivityEventResponse, status_code=status.HTTP_201_CREATED)
async def add_item_comment(
    id: str,
    payload: CommentCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    item = (await db.execute(select(WorkItem).where(WorkItem.id == id))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work item not found.")

    if not current_user.has_team_access(item.team_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: You are not in this team.")
    if not current_user.can_mutate(item.team_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: Viewer cannot add comments.")

    now = datetime.now(timezone.utc)
    event = ActivityEvent(
        id=str(uuid.uuid4()),
        work_item_id=id,
        actor_id=current_user.id,
        event_type="commented",
        old_value=None,
        new_value=None,
        comment_body=payload.comment,
        created_at=now
    )
    db.add(event)
    await db.commit()
    await db.refresh(event, ["actor"])
    return serialize_activity(event)

@router.post("/admin/clear-all")
async def clear_all_items(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Administrative reset endpoint to clear all work items, events, and jobs for clean testing."""
    from sqlalchemy import delete
    await db.execute(delete(ActivityEvent))
    await db.execute(delete(OutboxJob))
    await db.execute(delete(IdempotencyKey))
    await db.execute(delete(WorkItem))
    await db.commit()
    return {"status": "ok", "message": "All work items, activity events, and outbox jobs have been wiped. Board is a blank slate."}

@router.post("/admin/reseed")
async def reseed_database_endpoint(
    count: int = 50,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Seed sample items on demand."""
    from app.seed import seed_database
    await seed_database(count)
    return {"status": "ok", "message": f"Successfully seeded {count} sample items."}
