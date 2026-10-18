import asyncio
import random
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from app.core.security import hash_password
from app.database import engine, AsyncSessionLocal, Base
from app.models import User, Team, Membership, WorkItem, ActivityEvent

DEFAULT_PASSWORD_HASH = hash_password("password123")

TEAMS_DATA = [
    {"name": "Core Infrastructure & Ops", "description": "Platform availability, Kubernetes, deployments and database management"},
    {"name": "Incident Response", "description": "Live production alerts, 24/7 triage, mitigation and postmortems"},
    {"name": "Payments & Billing Ops", "description": "Payment gateways, reconciliation discrepancies and chargeback disputes"},
    {"name": "Compliance & Security", "description": "Audit readiness, SOC2/GDPR compliance checks and access reviews"},
]

USERS_DATA = [
    {"email": "admin@neohelp.io", "full_name": "Alice Johnson", "roles": {"Core Infrastructure & Ops": "Admin", "Compliance & Security": "Lead"}},
    {"email": "lead.core@neohelp.io", "full_name": "Bob Smith", "roles": {"Core Infrastructure & Ops": "Lead", "Incident Response": "Member"}},
    {"email": "member.core@neohelp.io", "full_name": "Charlie Davis", "roles": {"Core Infrastructure & Ops": "Member"}},
    {"email": "lead.incident@neohelp.io", "full_name": "Diana Prince", "roles": {"Incident Response": "Lead", "Core Infrastructure & Ops": "Member"}},
    {"email": "member.incident@neohelp.io", "full_name": "Evan Wright", "roles": {"Incident Response": "Member"}},
    {"email": "lead.payments@neohelp.io", "full_name": "Fiona Gallagher", "roles": {"Payments & Billing Ops": "Lead"}},
    {"email": "member.payments@neohelp.io", "full_name": "George Clark", "roles": {"Payments & Billing Ops": "Member"}},
    {"email": "lead.compliance@neohelp.io", "full_name": "Hannah Abbott", "roles": {"Compliance & Security": "Lead"}},
    {"email": "member.compliance@neohelp.io", "full_name": "Ian Malcolm", "roles": {"Compliance & Security": "Member"}},
    {"email": "viewer.global@neohelp.io", "full_name": "Julia Roberts", "roles": {
        "Core Infrastructure & Ops": "Viewer",
        "Incident Response": "Viewer",
        "Payments & Billing Ops": "Viewer",
        "Compliance & Security": "Viewer"
    }},
]

ITEM_TYPES = ["incident", "customer_issue", "payment", "compliance", "task"]
PRIORITIES = ["low", "medium", "high", "urgent"]
STATUSES = ["Open", "In Progress", "Awaiting Approval", "Resolved", "Closed"]

SAMPLE_TITLES = {
    "Core Infrastructure & Ops": [
        "Kubernetes worker node high memory threshold",
        "PostgreSQL read replica replication lag > 500ms",
        "Ingress TLS certificate rotation drill",
        "Redis cluster slot reallocation verification",
        "Egress NAT gateway throughput saturation warning",
        "Staging environment ephemeral DB teardown failure",
        "Elasticsearch shard reallocation after disk expansion",
        "Multi-region VPC peering routing latency degradation"
    ],
    "Incident Response": [
        "Elevated 5xx HTTP response rate on authentication service",
        "DDoS mitigation rate-limiter false positive block on API v2",
        "Webhook delivery worker queue length surge above 10k",
        "Downstream third-party SMS provider latency spike",
        "Checkout service degraded response time during flash sale",
        "Edge CDN cache invalidation backlog failure",
        "Memory leak in streaming metrics aggregator pod",
        "DNS lookup resolution timeout in EU-Central datacenter"
    ],
    "Payments & Billing Ops": [
        "Stripe webhook chargeback reconciliation mismatch",
        "Adyen batch settlement file parsing error line 4402",
        "Refund execution deadlock on concurrent idempotency retry",
        "SEPA direct debit mandate expiration notice generation",
        "Foreign currency exchange rate oracle update stale",
        "Double deduction report on subscription invoice #INV-9821",
        "Payout batch hold pending anti-fraud sanction screening",
        "Payment gateway fallback circuit breaker tripped"
    ],
    "Compliance & Security": [
        "SOC2 Trust Services Criteria quarterly evidence collection",
        "GDPR Right to Be Forgotten deletion request token #DEL-310",
        "Unapproved privileged IAM access policy modification detected",
        "Quarterly penetration test critical finding remediation",
        "Vendor security assessment renewal for Cloudflare",
        "Production database access log audit anomaly check",
        "Employee offboarding cryptographic token revocation verify",
        "Annual disaster recovery failover drill documentation"
    ]
}

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables initialized.")

async def seed_database(target_items: int = 2500):
    await init_db()

    async with AsyncSessionLocal() as session:
        # Check if already seeded
        result = await session.execute(select(func.count(WorkItem.id)))
        current_count = result.scalar()
        if current_count >= target_items:
            print(f"Database already contains {current_count} work items. Skipping seed.")
            return

        print(f"Current work items: {current_count}. Proceeding with mock seed...")

        # 1. Create Teams
        teams_map = {}
        for t_data in TEAMS_DATA:
            res = await session.execute(select(Team).where(Team.name == t_data["name"]))
            team = res.scalar_one_or_none()
            if not team:
                team = Team(name=t_data["name"], description=t_data["description"])
                session.add(team)
                await session.flush()
            teams_map[team.name] = team
        print(f"Seeded {len(teams_map)} teams.")

        # 2. Create Users & Memberships
        users_map = {}
        for u_data in USERS_DATA:
            res = await session.execute(select(User).where(User.email == u_data["email"]))
            user = res.scalar_one_or_none()
            if not user:
                user = User(
                    email=u_data["email"],
                    password_hash=DEFAULT_PASSWORD_HASH,
                    full_name=u_data["full_name"]
                )
                session.add(user)
                await session.flush()
            users_map[user.email] = user

            # Create memberships
            for team_name, role in u_data["roles"].items():
                team = teams_map.get(team_name)
                if team:
                    mem_res = await session.execute(
                        select(Membership).where(
                            Membership.user_id == user.id,
                            Membership.team_id == team.id
                        )
                    )
                    if not mem_res.scalar_one_or_none():
                        session.add(Membership(
                            user_id=user.id,
                            team_id=team.id,
                            role=role
                        ))
        await session.flush()
        print(f"Seeded {len(users_map)} users with multi-team memberships.")

        # 3. Create 2,500+ Work Items with initial Activity Events
        items_to_create = target_items - current_count
        print(f"Generating {items_to_create} work items...")

        now = datetime.now(timezone.utc)
        user_ids = [u.id for u in users_map.values()]
        teams_list = list(teams_map.values())

        batch_size = 500
        total_created = 0

        for batch_start in range(0, items_to_create, batch_size):
            batch_count = min(batch_size, items_to_create - batch_start)
            items_batch = []
            events_batch = []

            for i in range(batch_count):
                item_idx = current_count + batch_start + i + 1
                team = random.choice(teams_list)
                creator_id = random.choice(user_ids)
                assignee_id = random.choice(user_ids + [None, None]) # 33% unassigned
                item_type = random.choice(ITEM_TYPES)
                priority = random.choice(PRIORITIES)
                status = random.choice(STATUSES)
                version = random.randint(1, 4)

                # Random creation date over past 60 days
                created_delta = timedelta(days=random.randint(0, 60), hours=random.randint(0, 23), minutes=random.randint(0, 59))
                item_created_at = now - created_delta
                due_date = item_created_at + timedelta(days=random.randint(1, 14)) if random.random() > 0.3 else None

                base_title = random.choice(SAMPLE_TITLES[team.name])
                title = f"[{team.name[:4].upper()}-{item_idx:04d}] {base_title} #{item_idx}"
                desc = (
                    f"Operational tracking item #{item_idx} coordinates remediation, "
                    f"cross-team alignment, and SLA compliance within {team.name}. "
                    f"Priority set to {priority.upper()} with active state {status}."
                )

                item_id = str(uuid.uuid4())
                work_item = WorkItem(
                    id=item_id,
                    title=title,
                    description=desc,
                    type=item_type,
                    priority=priority,
                    status=status,
                    team_id=team.id,
                    assignee_id=assignee_id,
                    created_by_id=creator_id,
                    due_date=due_date,
                    version=version,
                    created_at=item_created_at,
                    updated_at=item_created_at + timedelta(minutes=random.randint(5, 300))
                )
                items_batch.append(work_item)

                # Append-only creation activity event
                event_create = ActivityEvent(
                    id=str(uuid.uuid4()),
                    work_item_id=item_id,
                    actor_id=creator_id,
                    event_type="created",
                    old_value=None,
                    new_value={"status": "Open", "priority": priority, "type": item_type},
                    comment_body="Operational task initialized in system feed.",
                    created_at=item_created_at
                )
                events_batch.append(event_create)

                # If assigned, append assignment event
                if assignee_id:
                    event_assign = ActivityEvent(
                        id=str(uuid.uuid4()),
                        work_item_id=item_id,
                        actor_id=assignee_id,
                        event_type="claimed" if assignee_id == creator_id else "assigned",
                        old_value={"assignee_id": None},
                        new_value={"assignee_id": assignee_id},
                        comment_body="Item claimed by operator for immediate investigation.",
                        created_at=item_created_at + timedelta(minutes=random.randint(2, 30))
                    )
                    events_batch.append(event_assign)

                # If status changed from Open, add transition event
                if status != "Open":
                    event_trans = ActivityEvent(
                        id=str(uuid.uuid4()),
                        work_item_id=item_id,
                        actor_id=assignee_id or creator_id,
                        event_type="transitioned",
                        old_value={"status": "Open"},
                        new_value={"status": status},
                        comment_body=f"Workflow transitioned to state: {status}.",
                        created_at=item_created_at + timedelta(minutes=random.randint(35, 120))
                    )
                    events_batch.append(event_trans)

            session.add_all(items_batch)
            session.add_all(events_batch)
            await session.commit()
            total_created += batch_count
            print(f"Committed batch: {total_created}/{items_to_create} work items + activity events.")

        print(f"Successfully seeded database with {total_created} items!")

if __name__ == "__main__":
    asyncio.run(seed_database(2500))
