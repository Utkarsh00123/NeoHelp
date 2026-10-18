# Engineering Decisions Log — Newtonite Operations (`newtonite-ops-<2300971530133>`)

This document tracks foundational architectural decisions across development phases following the **Context, Options, Choice, Trade-off** framework.

---

### Decision 1: Monorepo Architecture & Single-Command Docker Orchestration
* **Context (Phase 1):** Reviewers and operators require zero-friction deployment to spin up the entire operational timeline stack (PostgreSQL, Redis, FastAPI, React + Vite) without manual environment dependency installations.
* **Options:**
  1. Separate repositories for backend and frontend with distinct deployment guides.
  2. Monorepo with manual local startup (`npm run dev` + `uvicorn`).
  3. Unified monorepo with `docker-compose.yml` leveraging Docker healthcheck gating and volume binds.
* **Choice:** Option 3. Orchestrated via `docker compose up --build` with declarative health probes on Postgres (`pg_isready`) and Redis (`ping`).
* **Trade-off:** Initial Docker build takes ~1–2 minutes, but provides 100% environment parity, zero port collision surprises, and guaranteed cross-service networking.

---

### Decision 2: Relational Data Model with Immutability & Concurrency Control
* **Context (Step 2 / Phase 2):** High-velocity incident response and compliance workflows face race conditions (concurrent claims, stale updates) and require an unimpeachable audit trail of all historical activities.
* **Options:**
  1. In-place mutating rows with simple `updated_at` timestamps (Plain CRUD).
  2. Event sourcing only (reconstructing state entirely from append-only events).
  3. Hybrid normalized schema: Current state in `work_items` with integer `version` locking + append-only `activity_events` committed in the exact same database transaction.
* **Choice:** Option 3. Atomic hybrid model. Every transition, assignment, or edit writes both the state change and an `activity_events` record within a single ACID transaction.
* **Trade-off:** Dual-writes require strict transaction management in application code, but prevent out-of-sync timeline history and keep query performance fast for dashboard lists.

---

### Decision 3: Multi-Role Team Membership & Server-Side RBAC Scoping
* **Context (Step 2 / Phase 2):** Users operate across multiple departments with different authority levels (e.g. Lead in Compliance, Member in Incident Response, Viewer in Infrastructure).
* **Options:**
  1. Global user roles (`admin`, `user`).
  2. Client-side role gating (hiding buttons in React).
  3. Relational `memberships` table mapping `(user_id, team_id, role)` with server-side validation dependencies.
* **Choice:** Option 3. Strict normalized `memberships` table with unique constraint `(user_id, team_id)`. The backend verifies team membership and role on every read/write.
* **Trade-off:** Requires joining memberships or loading user team-role mappings on requests, but guarantees unauthorized users cannot access or alter cross-team items.

---

### Decision 4: High-Performance Composite Indexing for Cursor Pagination
* **Context (Step 2 / Phase 2):** The system is built for tens of thousands of work items and growing event logs. Offset-based pagination (`OFFSET 5000`) degrades severely at scale and causes page drift under rapid inserts.
* **Options:**
  1. Standard offset-limit pagination (`LIMIT 20 OFFSET N`).
  2. In-memory frontend filtering of loaded records.
  3. Server-side keyset/cursor pagination backed by composite index `(team_id, status, priority, id)`.
* **Choice:** Option 3. Composite indexing on `(team_id, status, priority, id)` and `(work_item_id, created_at)` for event streams.
* **Trade-off:** Slightly increased index storage overhead, but query execution remains constant $O(\log N)$ regardless of database depth.

---

### Decision 5: Idempotency Key & Transactional Outbox Schema
* **Context (Step 2 / Phase 2):** Network blips and retries can trigger duplicate item creations or repeated notifications.
* **Options:**
  1. Client-side debounce only.
  2. Direct Redis publish during HTTP request lifecycle without transactional safety.
  3. Relational `idempotency_keys` table and `outbox_jobs` table processed asynchronously by worker.
* **Choice:** Option 3. Mutating requests evaluate `idempotency_keys` with payload hashing. Asynchronous side-effects write to `outbox_jobs` with a `dedupe_key` in the same DB transaction.
* **Trade-off:** Small write amplification per mutation, but guarantees exactly-once processing semantics and atomic consistency even if the background broker is momentarily unavailable.

---

### Decision 6: Centralized Token Authentication & Resource-Level RBAC Guard
* **Context (Step 3 / Phase 3):** To avoid unauthorized read/write access across teams and guarantee that role privileges (Viewer read-only, Member transition limits, Lead approval requirements) are tamper-proof, authorization must be validated strictly on the server.
* **Options:**
  1. Ad-hoc authorization logic inside individual route handler functions.
  2. Frontend UI gating only (hiding buttons and fields).
  3. Centralized `AuthenticatedUser` model and `require_team_role` dependency with role hierarchy mapping (`Admin > Lead > Member > Viewer`).
* **Choice:** Option 3. Central dependency checks JWT token, loads user memberships, and evaluates permission thresholds on every operation. Non-members receive immediate `403 Forbidden` on read/write; Viewers are blocked from mutating actions; Leads are required for state approval and resolution.
* **Trade-off:** Fast validation requires loading membership relations on authenticated requests, but completely eliminates cross-tenant data leakage and privilege escalation vulnerabilities.
