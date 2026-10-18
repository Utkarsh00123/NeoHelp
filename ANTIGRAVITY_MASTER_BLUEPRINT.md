1. Architectural Constraints & Tech Stack
Backend: FastAPI (Python)

Database: PostgreSQL

ORM: SQLAlchemy (with async support if preferred, or synchronous, but strictly handle transactions)

Frontend: React + TanStack Query (Vite based)

Async/Jobs: Redis (for background workers via a transactional outbox pattern)

Testing: Pytest (API-level tests for critical behaviors)

Infrastructure: Docker Compose (must spin up Postgres, Redis, Backend, and Frontend in one command)

UI/UX Theme: "Timeline-based website". The application must visually prioritize the chronology of events. The main dashboard should feature a timeline feed of urgent operational items, and the individual work item view must be a rich vertical timeline of activity history, comments, and state transitions.

2. Strict Rules for Every Iteration (Check Before Proceeding)
You must enforce these rules in every file you generate or modify:

No Plain CRUD: Operations must handle edge cases. You must never generate a simple UPDATE without a version check or a POST without an idempotency check.

Server-Side Enforcement: Do not rely on hiding UI buttons. Role-based access control (RBAC) and state transition logic MUST be strictly validated on the FastAPI backend.

Atomic Transactions: Every modification to a work_item (e.g., claim, edit, transition) MUST be wrapped in a database transaction that simultaneously writes an activity_event row. The timeline history must never disagree with the item's current state.

Pagination & Indexing: Never load all items into memory. All list endpoints must use server-side cursor pagination, filtering, and database indexing.

Strictly Excluded Features: DO NOT implement user registration (seed users instead), SSO, email delivery, file attachments, or real-time WebSockets (use polling/refetching via TanStack Query).

3. Core Data Model Requirements
Users & Teams: users, teams, memberships (user_id, team_id, role: Viewer, Member, Lead, Admin).

Work Items: work_items (id, title, description, type, priority, status, team_id, assignee_id, creator_id, due_date, version).

Activity/Timeline: activity_events (id, item_id, actor_id, event_type, old_state, new_state, timestamp, comment).

Idempotency: idempotency_keys (key, response_body, status_code).

Outbox: outbox_jobs (id, payload, status, retries).

4. Main Flow of Project Creation
Phase 1: Project Setup & Infrastructure
Create the monorepo structure (/backend, /frontend).

Write the docker-compose.yml containing PostgreSQL, Redis, FastAPI backend, and React frontend.

Configure basic FastAPI setup and React + Vite + TanStack Query boilerplate.

Phase 2: Database Schema, ORM, and Seeding
Define SQLAlchemy models according to the core data model requirements.

Implement a robust database migration/initialization script.

Create a strict seeder script: create 3-4 teams, ~10 users with varying roles across those teams, and ~2,000 sample work items to prove server-side pagination works.

Phase 3: Auth & Resource-Level Authorization (Critical Behavior 1)
Implement a mocked token-based login (e.g., return a JWT or simple session token for the seeded users).

Write FastAPI dependencies (Depends) that load the user's team roles.

Ensure every endpoint scopes database queries to the user's teams. A user outside a team must receive a 403/404 on read/write.

Phase 4: Core API & Critical Behaviors
Implement the work item endpoints with the following critical concurrency behaviors:

Concurrent Claims (Critical Behavior 2): Implement POST /items/{id}/claim. Use a conditional SQLAlchemy update (UPDATE ... WHERE id = :id AND assignee_id IS NULL). If 0 rows update, throw a 409 Conflict.

Stale Edits (Critical Behavior 3): Implement optimistic locking on PATCH /items/{id}. The client sends a version. Update strictly WHERE id = :id AND version = :version, then increment the version. Mismatch throws a 409.

Idempotency (Critical Behavior 4): Implement an Idempotency-Key header check for creation/action endpoints. Store the key and response; return the stored response if the key is reused.

Workflow Rules: Implement POST /items/{id}/transition. Enforce valid state jumps (e.g., Open -> In Progress -> Awaiting Approval). Enforce that moving to Resolved requires a user with the Lead role for that specific team.

Phase 5: Reliable Async Work (Critical Behavior 5)
Implement a Transactional Outbox. When a work item is created or reassigned, write an outbox record in the SAME SQLAlchemy transaction.

Create a Redis-backed background worker (using rq, Celery, or a simple custom Redis loop) that reads the outbox, processes the job (e.g., printing a mocked notification to the console), handles retries with backoff, and marks it completed.

Phase 6: Frontend Construction (Timeline Theme)
API Integration: Setup TanStack Query hooks for fetching and mutating data. Handle 409 errors gracefully by prompting the user "This item was updated by someone else, please refresh."

Dashboard: Build a timeline-oriented dashboard. Show a unified feed of "Assigned to me", "Unassigned urgent", and "Awaiting my approval". Implement server-side filtering and cursor pagination controls.

Item Detail (The Timeline): Build the core view. At the top, show the item's current state. Below it, render a rich vertical timeline mapping every row from activity_events so users can seamlessly read the history of state changes, ownership transfers, and comments.

Phase 7: Pytest Test Suite
Write automated tests specifically targeting the dangerous behaviors:

Fire two claim requests concurrently; assert exactly one succeeds and the other gets a 409.

Send an update with an old version integer; assert it is rejected.

Send the same Idempotency-Key twice; assert only one database row is created.

Attempt an invalid workflow transition or non-Lead approval; assert 403/400.

Attempt to read/write an item belonging to a team the mock user is not in; assert 403.