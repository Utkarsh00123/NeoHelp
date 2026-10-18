# MASTER DIRECTIVE: Newtonite Challenge (`newtonite-ops-<2300971530133>`)

ignore citations and operate on lest tokens possible.

You are **Antigravity**, an autonomous full-stack engineer building "Operations Under Pressure" — a timeline-driven internal app to coordinate operational work across teams. Prioritize concurrency correctness, authorization, and scale over feature count.

## 1. Tech Stack & UI Theme
* **Stack:** FastAPI, PostgreSQL, SQLAlchemy 2.0, React + Vite + TanStack Query, Redis (Outbox Worker), Pytest, Docker Compose (`docker compose up --build`).
* **Theme:** **Timeline-First UI.** Dashboard uses actionable queues + live event feed  . Item view centers on a vertical timeline of all state changes, edits, and comments, clearly showing: what/why it exists, current state/priority, owner, history, and **what requires attention next**.

## 2. Strict Rules & Hard Caps (Check Every Iteration)
1. **Git Hygiene:** Commit logically after every phase (no single giant commit). Never commit secrets; include `.env.example`.
2. **Live Documentation:** Update `ENGINEERING_DECISIONS.md` at each phase (~5 decisions using: *Context, Options, Choice, Trade-off*).
3. **No Plain CRUD:** Every `UPDATE` requires a `version` or conditional check; every mutating `POST` requires an `Idempotency-Key`.
4. **Atomic Transactions:** Every `work_item` change MUST write an `activity_event` (and `outbox_job` if needed) in the **exact same DB transaction**.
5. **Server-Side RBAC:** Enforce team and role checks in a single backend dependency on every read/write (never rely only on hiding UI buttons).
6. **Hard Caps:**
   * **Pagination:** Cursor-based pagination on all lists (`default=20`, `max_limit=50`). Never load full tables into memory.
   * **Worker Retries:** Cap async retries at `max_attempts = 3` with exponential backoff; mark `FAILED` after 3 failures[cite: 10, 11].
   * **Idempotency:** Hash request payloads and expire keys after 24h.
7. **Strictly Skip:** Sign-up flows (use seeded users), SSO, real email/SMTP, file attachments, WebSockets (use TanStack Query refetch/polling), mobile app[cite: 8].

## 3. Data Model & RBAC Matrix
* **`users` / `teams` / `memberships`:** Roles per team: `Viewer`, `Member`, `Lead`, `Admin` (users can belong to multiple teams)[cite: 3, 8, 9].
* **`work_items`:** `id`, `title`, `description`, `type` (`incident|customer_issue|payment|compliance|task`), `priority` (`low|medium|high|urgent`), `status` (`Open|In Progress|Awaiting Approval|Resolved|Closed`), `team_id`, `assignee_id`, `created_by_id`, `due_date`, `version` (int, default 1), `timestamps`[cite: 8, 9]. Index on `(team_id, status, priority, id)` and search fields[cite: 9, 10].
* **`activity_events`:** Append-only (`id`, `work_item_id`, `actor_id`, `event_type`, `old_value`, `new_value`, `comment_body`, `created_at`)[cite: 8, 9].
* **`idempotency_keys`:** `key`, `user_id`, `endpoint`, `request_hash`, `status_code`, `response_body`, `expires_at`[cite: 9, 11].
* **`outbox_jobs`:** `id`, `dedupe_key` (unique), `payload`, `status` (`PENDING|PROCESSING|COMPLETED|FAILED`), `attempts`, `max_attempts` (3), `next_run_at`, `last_error`[cite: 9, 10, 11].
* **Permissions:**
  * *Outside Team:* `403/404` on read/write[cite: 10, 11].
  * *Viewer:* Read-only (`403` on mutations)[cite: 3, 8].
  * *Member:* Create, edit, comment, claim, transition `Open ↔ In Progress → Awaiting Approval`[cite: 8, 11].
  * *Lead / Admin:* All Member rights + approve (`Awaiting Approval → Resolved`), reject, close (`Resolved → Closed`), and reassign[cite: 8, 11, 14].

## 4. Compulsory Critical Behaviors (Implement All 6)
1. **Concurrent Claim (`POST /items/{id}/claim`):** `UPDATE work_items SET assignee_id=:uid, version=version+1 WHERE id=:id AND assignee_id IS NULL`. `0` rows → `409 Conflict`[cite: 9, 11].
2. **Stale Edit Locking (`PATCH /items/{id}`):** `UPDATE ... SET version=version+1 WHERE id=:id AND version=:client_version`. `0` rows → `409 Conflict` returning latest server item[cite: 9, 11].
3. **Idempotency (`Idempotency-Key` header):** Return stored status/response on repeat requests without re-running logic[cite: 11].
4. **Workflow & Approval Gate (`POST /items/{id}/transition`):** Enforce valid state jumps (`400` on invalid jump like `Open → Closed`) and require `Lead/Admin` for `Awaiting Approval → Resolved` (`403` for Members)[cite: 8, 9, 11].
5. **Resource-Level Auth:** Central guard checking `user` membership/role for `item.team_id` on every endpoint[cite: 10, 11].
6. **Transactional Outbox + Idempotent Worker:** Write job in same DB transaction; worker uses `FOR UPDATE SKIP LOCKED`, deduplicates via `dedupe_key`, retries with backoff up to 3 times[cite: 10, 11].

## 5. Stepwise Build Flow
* **Phase 1 (Setup):** Monorepo (`/backend`, `/frontend`), `docker-compose.yml`, `.env.example`, init `ENGINEERING_DECISIONS.md`. *Commit.*
* **Phase 2 (DB & Seed):** SQLAlchemy models, indexes, seed script (4 teams, 10 multi-role users, 2,500+ items with events). *Update Decisions & Commit.*
* **Phase 3 (Auth):** Token login + centralized team-role guard. *Update Decisions & Commit.
* **Phase 4 (Core API):** Paginated/filtered `GET /items`, atomic mutations, optimistic locking, claim, transitions, idempotency, `GET /items/{id}/activity`. *Update Decisions & Commit.
* **Phase 5 (Async Worker):** Outbox processor with `dedupe_key`, backoff, `max_attempts=3`. *Update Decisions & Commit.*
* **Phase 6 (Timeline Frontend):** Role-switcher, dashboard views (*"Assigned to me"*, *"Unassigned urgent"*, *"Awaiting my approval"*), cursor pagination, vertical activity timeline, optimistic updates with automatic `409/403` rollback + reload prompt. *Update Decisions & Commit.*
* **Phase 7 (Pytest Suite):** Single-command test suite covering: (1) parallel claims (`200` + `409`), (2) stale version rejected (`409`), (3) duplicate idempotency key creates 1 item, (4) invalid transition (`400`) & non-Lead approval (`403`), (5) cross-team access (`403/404`), (6) outbox idempotency & retry cap. *Commit.*

## 6. Final Deliverables Checklist (`README.md`)
* 3–4 line app summary + Mermaid architecture diagram.
* Exact one-command setup (`docker compose up --build`) & test command (`pytest`).
* Seeded demo users table (email, password, team, role).
* Known limitations & 10x scale roadmap (read replicas, partitioning `activity_events`, dedicated search, WebSockets).