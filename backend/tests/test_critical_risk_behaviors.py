import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app

async def login_user(client: AsyncClient, email: str) -> str:
    res = await client.post("/api/auth/login", json={"email": email, "password": "password123"})
    return res.json()["access_token"]

@pytest.mark.asyncio
async def test_scenario_1_concurrent_claims():
    """Scenario 1: Fire two parallel claim requests; verify exactly one succeeds while the other is rejected with 409."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create unassigned item
        token_diana = await login_user(client, "lead.incident@neohelp.io")
        user_info = (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_diana}"})).json()
        team_id = user_info["memberships"][0]["team_id"]

        create_res = await client.post(
            "/api/items",
            json={
                "title": "Incident Triage Claim Race",
                "description": "Simultaneous claim test item.",
                "type": "incident",
                "priority": "urgent",
                "team_id": team_id
            },
            headers={"Authorization": f"Bearer {token_diana}"}
        )
        item_id = create_res.json()["id"]

        token_evan = await login_user(client, "member.incident@neohelp.io")

        # Fire two parallel claim requests
        res1, res2 = await asyncio.gather(
            client.post(f"/api/items/{item_id}/claim", headers={"Authorization": f"Bearer {token_diana}"}),
            client.post(f"/api/items/{item_id}/claim", headers={"Authorization": f"Bearer {token_evan}"}),
            return_exceptions=False
        )

        statuses = {res1.status_code, res2.status_code}
        assert statuses == {200, 409}, f"Expected one 200 and one 409, got {res1.status_code} and {res2.status_code}"

@pytest.mark.asyncio
async def test_scenario_2_stale_edits_rejected_and_data_unchanged():
    """Scenario 2: Send an update with an outdated version number; verify the server rejects it (409) and data remains unchanged."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await login_user(client, "member.core@neohelp.io")
        user_info = (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})).json()
        team_id = user_info["memberships"][0]["team_id"]

        create_res = await client.post(
            "/api/items",
            json={
                "title": "Original Title v1",
                "description": "Original Description v1",
                "type": "task",
                "priority": "low",
                "team_id": team_id
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        item_id = create_res.json()["id"]

        # Valid update increments version to 2
        up1 = await client.patch(
            f"/api/items/{item_id}",
            json={"version": 1, "title": "Updated Title v2"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert up1.status_code == 200
        assert up1.json()["version"] == 2

        # Stale update sending old version 1 -> Must reject with 409
        stale_res = await client.patch(
            f"/api/items/{item_id}",
            json={"version": 1, "title": "Malicious Stale Override"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert stale_res.status_code == 409

        # Verify data remains unchanged in database
        check_res = await client.get(f"/api/items/{item_id}", headers={"Authorization": f"Bearer {token}"})
        assert check_res.json()["title"] == "Updated Title v2"
        assert check_res.json()["version"] == 2

@pytest.mark.asyncio
async def test_scenario_3_idempotency_duplicate_key_prevents_duplicate_items():
    """Scenario 3: Transmit the same Idempotency-Key twice; verify only one item is created and identical response returned."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await login_user(client, "lead.payments@neohelp.io")
        user_info = (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})).json()
        team_id = user_info["memberships"][0]["team_id"]

        idempotency_header = {"Authorization": f"Bearer {token}", "Idempotency-Key": "unique-idemp-key-5555"}
        payload = {
            "title": "Payment Settlement Reconciliation Item",
            "description": "Testing idempotency deduplication across retries.",
            "type": "payment",
            "priority": "high",
            "team_id": team_id
        }

        # First request
        res1 = await client.post("/api/items", json=payload, headers=idempotency_header)
        assert res1.status_code == 201
        item_id = res1.json()["id"]

        # Second request (retry)
        res2 = await client.post("/api/items", json=payload, headers=idempotency_header)
        assert res2.status_code in [200, 201]
        assert res2.json()["id"] == item_id
        assert res2.json()["title"] == payload["title"]

@pytest.mark.asyncio
async def test_scenario_4_workflow_rules_and_authorization_matrix():
    """Scenario 4: Verify invalid state jumps are rejected (400), non-Lead approvals fail (403), and cross-team access fails (403)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token_member = await login_user(client, "member.compliance@neohelp.io")
        token_lead = await login_user(client, "lead.compliance@neohelp.io")
        token_outsider = await login_user(client, "member.core@neohelp.io")  # Not in Compliance

        user_info = (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_member}"})).json()
        compliance_team_id = user_info["memberships"][0]["team_id"]

        # Create Open item
        create_res = await client.post(
            "/api/items",
            json={
                "title": "SOC2 Evidence Review Gate",
                "type": "compliance",
                "priority": "high",
                "team_id": compliance_team_id
            },
            headers={"Authorization": f"Bearer {token_member}"}
        )
        item_id = create_res.json()["id"]

        # 4a: Cross-team access denied (403)
        cross_team_res = await client.get(
            f"/api/items/{item_id}",
            headers={"Authorization": f"Bearer {token_outsider}"}
        )
        assert cross_team_res.status_code == 403

        # 4b: Invalid state jump (Open -> Resolved) -> 400 Bad Request
        invalid_jump = await client.post(
            f"/api/items/{item_id}/transition",
            json={"target_status": "Resolved"},
            headers={"Authorization": f"Bearer {token_member}"}
        )
        assert invalid_jump.status_code == 400

        # Move Open -> In Progress -> Awaiting Approval
        await client.post(f"/api/items/{item_id}/transition", json={"target_status": "In Progress"}, headers={"Authorization": f"Bearer {token_member}"})
        await client.post(f"/api/items/{item_id}/transition", json={"target_status": "Awaiting Approval"}, headers={"Authorization": f"Bearer {token_member}"})

        # 4c: Non-Lead approval fails (403 Forbidden)
        non_lead_approval = await client.post(
            f"/api/items/{item_id}/transition",
            json={"target_status": "Resolved"},
            headers={"Authorization": f"Bearer {token_member}"}
        )
        assert non_lead_approval.status_code == 403

        # 4d: Lead approval succeeds (200 OK)
        lead_approval = await client.post(
            f"/api/items/{item_id}/transition",
            json={"target_status": "Resolved", "comment": "Approved by Compliance Lead."},
            headers={"Authorization": f"Bearer {token_lead}"}
        )
        assert lead_approval.status_code == 200
        assert lead_approval.json()["status"] == "Resolved"
