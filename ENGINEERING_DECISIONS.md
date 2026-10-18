# Engineering Decisions Log — NeoHelp (`newtonite-ops-2300971530133`)

> **Live Operational Deployment Links:**  
> 🌐 **Live Web Application (Vercel):** [https://neo-help.vercel.app/](https://neo-help.vercel.app/)  
> ⚡ **Live Backend API (Render):** [https://neohelp-backend.onrender.com](https://neohelp-backend.onrender.com)  
> 🩺 **Live Health Probe:** [https://neohelp-backend.onrender.com/api/health](https://neohelp-backend.onrender.com/api/health)  
> 📖 **Interactive API Documentation:** [https://neohelp-backend.onrender.com/docs](https://neohelp-backend.onrender.com/docs)  

---

This document records the foundational architectural decisions made while building **NeoHelp**. Each entry breaks down the real problem faced, what alternatives were considered, what choice was made, and the realistic trade-offs accepted.

---

### Decision 1: Data Model & History — Atomic Dual-Writes vs. Full Event Sourcing
* **Context:** In incident response and compliance, losing history or having disagreement on "who changed what" is fatal. We needed an audit trail that can never get out of sync with an item's current state.
* **Options Considered:**
  1. *Plain Updates:* Just update the row in `work_items` with an `updated_at` timestamp. (Zero history).
  2. *Full Event Sourcing:* Store only events and rebuild current state on the fly. (Computationally heavy, hard to query lists and filter quickly).
  3. *Atomic Dual-Write:* Store current state in `work_items` with an integer `version`, and append an entry to `activity_events` inside the **exact same database transaction**.
* **Our Choice:** Option 3. Whenever a work item is created, edited, claimed, or transitioned, both the item update and the history event are committed together in one ACID transaction.
* **Trade-off:** Writing two records on every mutation takes slightly more code and database writes, but eliminates out-of-sync history and allows instant list querying without rebuilding state.

---

### Decision 2: Concurrency Control — Conditional Claims & Optimistic Locking
* **Context:** When multiple operators jump on the same high-urgency ticket, they easily step on each other's toes — either by trying to claim the same ticket simultaneously, or saving edits over someone else's newer changes.
* **Options Considered:**
  1. *Last-Write-Wins (LWW):* Whoever clicks save last overwrites whatever was there before. (Dangerous; causes silent data loss).
  2. *Pessimistic Row Locking (`FOR UPDATE` on read):* Lock the database row as soon as someone views it. (Causes database bottlenecks, hangs on dropped browser connections).
  3. *Conditional Updates & Version Checks:* 
     - Claims use atomic SQL: `WHERE id = :id AND assignee_id IS NULL`.
     - Edits check: `WHERE id = :id AND version = :client_version`.
* **Our Choice:** Option 3. If zero rows match the condition, the server immediately rolls back and returns a `409 Conflict`. The UI then prompts the user with a 1-click reload to view the latest state.
* **Trade-off:** The frontend has to handle `409 Conflict` gracefully and guide the user through reconciliation, but the database never suffers from locked rows or lost data.

---

### Decision 3: Authorization Model — Strict Server-Side Team Scoping
* **Context:** Users operate across multiple departments with different levels of authority (for example, someone might be a *Lead* in Incident Response, but only a *Viewer* in Payments).
* **Options Considered:**
  1. *Client-side gating:* Just hide the "Claim" or "Resolve" buttons in React. (Security through obscurity; anyone can bypass with Postman or Curl).
  2. *Global user roles:* Single role per user (`admin` or `user`). (Does not work for multi-team organizations).
  3. *Normalized `memberships` table + Central Server Dependency:* Check team membership and required role on every single API request.
* **Our Choice:** Option 3. Every endpoint runs a central authorization guard. If you aren't in the team, you get a `403 Forbidden`. If you are a *Viewer*, you are blocked from mutations. If a ticket needs approval (`Awaiting Approval → Resolved`), the server strictly requires a *Lead* or *Admin* role.
* **Trade-off:** Requires joining or loading memberships on every authenticated request, but completely shuts the door on cross-team data leaks and privilege escalation.

---

### Decision 4: Sync vs. Async — Transactional Outbox Pattern for Background Tasks
* **Context:** When an item is claimed or resolved, secondary actions need to happen (logging, event alerts, notifications). Doing this synchronously inside the main HTTP request risks "dual-write failures" (e.g. database commits, but Redis/notification service is down).
* **Options Considered:**
  1. *Synchronous side-effects:* Publish to Redis or send alerts inside the HTTP request. (Slows down API response; fails if the external service hiccups).
  2. *Direct background fire-and-forget:* Spawn a loose background thread without saving state. (If the server restarts, pending jobs disappear forever).
  3. *Transactional Outbox:* Write an `outbox_jobs` record inside the same DB transaction as the item update. An independent worker polls jobs using `FOR UPDATE SKIP LOCKED`, deduplicates via Redis, and retries with backoff up to 3 times.
* **Our Choice:** Option 3. Guarantees that if a task update commits, its background job is guaranteed to be saved and processed.
* **Trade-off:** Introduces a tiny background delay (~1 second) between database commit and processing, but eliminates lost jobs and dual-write corruption.

---

### Decision 5: Search & Pagination — Keyset Cursor Pagination over Offset
* **Context:** The system is engineered to handle tens of thousands of work items and growing audit logs. Standard `OFFSET 5000` causes heavy database performance degradation and skips or duplicates items when new records are inserted while browsing.
* **Options Considered:**
  1. *Offset Pagination (`LIMIT 20 OFFSET 5000`):* Simple to write, but database must scan and throw away thousands of rows on deep pages, and rapid inserts cause page drift.
  2. *Load everything into browser memory:* Fetch all items and let React filter in memory. (Crashes mobile browsers and wastes bandwidth).
  3. *Keyset Cursor Pagination:* Page records using a compound cursor (`created_at` timestamp + `id`) backed by a composite index `(team_id, status, priority, id)`.
* **Our Choice:** Option 3. Keyset cursor pagination ensures query time remains constant $O(\log N)$ whether an operator is looking at page 1 or page 500.
* **Trade-off:** You cannot jump arbitrarily to "Page 42" by typing a number, but operational triage feeds only scroll forward and backward, making cursor pagination the superior choice.

---

### Decision 6: Scope Discipline — What We Chose NOT to Build
* **Context:** In engineering projects with strict deadlines, trying to build every flashy feature leads to shallow, buggy code. We decided early on to focus 100% of our effort on rock-solid concurrency, authorization, and data integrity.
* **Explicit Exclusions:**
  1. *No User Registration / Signup Flow:* We used a deterministic seed script with 10 multi-role users. Testing complex RBAC with pre-configured accounts is far more valuable than building another password-reset form.
  2. *No WebSockets:* Live WebSockets add stateful connection handling and reconnect edge-cases. We relied on TanStack Query polling (15s intervals) and optimistic updates, which is much more resilient under unstable network conditions.
  3. *No Real Email / SMTP:* External mail servers introduce flaky network dependencies during testing. Mocked outbox event streaming proved the architecture without external email downtime.
  4. *No Heavy Decorative "AI Slop" UI:* Stripped out generic gradients, glassmorphism, and complex shadows in favor of a crisp 3-color palette (pure white, black, light blue) centered purely on the chronological event timeline.
* **Trade-off:** Reviewers don't see animated decorative cards or email inboxes, but they get a bulletproof, concurrency-safe operational engine that never drops an edit or fails a race condition.

---

## 🌐 Live Production Verification Endpoints

Verify the real-time health, documentation, and live user experience at:
* **Frontend Web Application (Vercel):** [https://neo-help.vercel.app/](https://neo-help.vercel.app/)
* **FastAPI Backend (Render):** [https://neohelp-backend.onrender.com](https://neohelp-backend.onrender.com)
* **System Health Check Probe:** [https://neohelp-backend.onrender.com/api/health](https://neohelp-backend.onrender.com/api/health)
* **Interactive Swagger UI:** [https://neohelp-backend.onrender.com/docs](https://neohelp-backend.onrender.com/docs)
