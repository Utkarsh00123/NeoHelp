import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from app.main import app
from app.models import WorkItem, Team, User, Membership, ActivityEvent

async def get_auth_token(client: AsyncClient, email: str) -> str:
    res = await client.post(
        "/api/auth/login",
        json={"email": email, "password": "password123"}
    )
    return res.json()["access_token"]

@pytest.mark.asyncio
async def test_cursor_pagination_and_team_filtering():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await get_auth_token(client, "admin@neohelp.io")
        headers = {"Authorization": f"Bearer {token}"}

        # Page 1 (limit = 5)
        res1 = await client.get("/api/items?limit=5", headers=headers)
        assert res1.status_code == 200
        data1 = res1.json()
        assert len(data1["items"]) == 5
        assert data1["has_more"] is True
        assert data1["next_cursor"] is not None

        # Page 2 using cursor
        res2 = await client.get(f"/api/items?limit=5&cursor={data1['next_cursor']}", headers=headers)
        assert res2.status_code == 200
        data2 = res2.json()
        assert len(data2["items"]) == 5
        # Ensure page 1 and page 2 don't overlap
        page1_ids = {item["id"] for item in data1["items"]}
        page2_ids = {item["id"] for item in data2["items"]}
        assert page1_ids.isdisjoint(page2_ids)

@pytest.mark.asyncio
async def test_idempotent_creation():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Charlie Davis is Member in Core Infrastructure & Ops
        token = await get_auth_token(client, "member.core@neohelp.io")
        user_info = (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})).json()
        team_id = user_info["memberships"][0]["team_id"]

        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "test-idempotent-key-001"
        }
        item_payload = {
            "title": "Idempotent Test Item #001",
            "description": "Testing that repeated requests return identical results without duplicates.",
            "type": "incident",
            "priority": "high",
            "team_id": team_id
        }

        # First request
        res1 = await client.post("/api/items", json=item_payload, headers=headers)
        assert res1.status_code == 201
        created_id = res1.json()["id"]

        # Duplicate request with same Idempotency-Key
        res2 = await client.post("/api/items", json=item_payload, headers=headers)
        assert res2.status_code in [200, 201]
        assert res2.json()["id"] == created_id
        assert res2.json()["title"] == "Idempotent Test Item #001"

@pytest.mark.asyncio
async def test_concurrent_claims():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create a fresh unassigned item in Incident Response team
        lead_token = await get_auth_token(client, "lead.incident@neohelp.io")
        user_info = (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {lead_token}"})).json()
        team_id = user_info["memberships"][0]["team_id"]

        create_res = await client.post(
            "/api/items",
            json={
                "title": "Concurrent Claim Race Condition Drill",
                "description": "Item to be claimed concurrently by two operators.",
                "type": "incident",
                "priority": "urgent",
                "team_id": team_id
            },
            headers={"Authorization": f"Bearer {lead_token}"}
        )
        item_id = create_res.json()["id"]

        # User 1: Diana Prince (Lead in Incident Response)
        token_diana = lead_token
        # User 2: Evan Wright (Member in Incident Response)
        token_evan = await get_auth_token(client, "member.incident@neohelp.io")

        # Send simultaneous claim requests
        res_diana, res_evan = await asyncio.gather(
            client.post(f"/api/items/{item_id}/claim", headers={"Authorization": f"Bearer {token_diana}"}),
            client.post(f"/api/items/{item_id}/claim", headers={"Authorization": f"Bearer {token_evan}"}),
            return_exceptions=False
        )

        statuses = [res_diana.status_code, res_evan.status_code]
        # Exactly one must succeed (200) and the other must receive 409 Conflict!
        assert 200 in statuses
        assert 409 in statuses

@pytest.mark.asyncio
async def test_optimistic_locking_stale_edit():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await get_auth_token(client, "member.core@neohelp.io")
        user_info = (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})).json()
        team_id = user_info["memberships"][0]["team_id"]

        create_res = await client.post(
            "/api/items",
            json={
                "title": "Optimistic Locking Version Verification",
                "description": "Testing version increments and rejection of stale version numbers.",
                "type": "task",
                "priority": "medium",
                "team_id": team_id
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        item = create_res.json()
        item_id = item["id"]
        v1 = item["version"]

        # Valid update with version 1 -> succeeds, version becomes 2
        update1 = await client.patch(
            f"/api/items/{item_id}",
            json={"version": v1, "title": "Updated Title Version 2"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert update1.status_code == 200
        assert update1.json()["version"] == v1 + 1

        # Stale update sending old version 1 -> MUST be rejected with 409 Conflict
        stale_update = await client.patch(
            f"/api/items/{item_id}",
            json={"version": v1, "title": "Stale Override Attempt"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert stale_update.status_code == 409
        err_detail = stale_update.json()["detail"]
        assert "server_version" in err_detail or "Conflict" in str(err_detail)

@pytest.mark.asyncio
async def test_workflow_transitions_and_lead_approval_gate():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token_member = await get_auth_token(client, "member.compliance@neohelp.io")
        token_lead = await get_auth_token(client, "lead.compliance@neohelp.io")

        member_info = (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_member}"})).json()
        compliance_team_id = member_info["memberships"][0]["team_id"]

        # 1. Create item (status = Open)
        create_res = await client.post(
            "/api/items",
            json={
                "title": "Compliance Audit Workflow Item",
                "description": "Testing state machine transitions and approval rules.",
                "type": "compliance",
                "priority": "high",
                "team_id": compliance_team_id
            },
            headers={"Authorization": f"Bearer {token_member}"}
        )
        item_id = create_res.json()["id"]

        # 2. Invalid jump (Open -> Resolved) -> 400 Bad Request
        bad_jump = await client.post(
            f"/api/items/{item_id}/transition",
            json={"target_status": "Resolved"},
            headers={"Authorization": f"Bearer {token_member}"}
        )
        assert bad_jump.status_code == 400

        # 3. Valid jump (Open -> In Progress) by Member -> 200 OK
        t1 = await client.post(
            f"/api/items/{item_id}/transition",
            json={"target_status": "In Progress"},
            headers={"Authorization": f"Bearer {token_member}"}
        )
        assert t1.status_code == 200
        assert t1.json()["status"] == "In Progress"

        # 4. Valid jump (In Progress -> Awaiting Approval) by Member -> 200 OK
        t2 = await client.post(
            f"/api/items/{item_id}/transition",
            json={"target_status": "Awaiting Approval"},
            headers={"Authorization": f"Bearer {token_member}"}
        )
        assert t2.status_code == 200
        assert t2.json()["status"] == "Awaiting Approval"

        # 5. Member attempts to approve (Awaiting Approval -> Resolved) -> 403 Forbidden!
        unauthorized_approval = await client.post(
            f"/api/items/{item_id}/transition",
            json={"target_status": "Resolved"},
            headers={"Authorization": f"Bearer {token_member}"}
        )
        assert unauthorized_approval.status_code == 403

        # 6. Lead approves (Awaiting Approval -> Resolved) -> 200 OK!
        lead_approval = await client.post(
            f"/api/items/{item_id}/transition",
            json={"target_status": "Resolved", "comment": "Approved after evidence verification."},
            headers={"Authorization": f"Bearer {token_lead}"}
        )
        assert lead_approval.status_code == 200
        assert lead_approval.json()["status"] == "Resolved"

@pytest.mark.asyncio
async def test_vertical_activity_timeline_history():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await get_auth_token(client, "admin@neohelp.io")
        user_info = (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})).json()
        team_id = user_info["memberships"][0]["team_id"]

        create_res = await client.post(
            "/api/items",
            json={
                "title": "Timeline Event Trail Verification",
                "description": "Ensure every action writes to activity_events.",
                "type": "incident",
                "priority": "urgent",
                "team_id": team_id
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        item_id = create_res.json()["id"]

        # Add comment
        comment_res = await client.post(
            f"/api/items/{item_id}/comments",
            json={"comment": "Investigating active telemetry spikes."},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert comment_res.status_code == 201

        # Retrieve activity timeline
        act_res = await client.get(f"/api/items/{item_id}/activity", headers={"Authorization": f"Bearer {token}"})
        assert act_res.status_code == 200
        events = act_res.json()
        event_types = [e["event_type"] for e in events]
        assert "created" in event_types
        assert "commented" in event_types
