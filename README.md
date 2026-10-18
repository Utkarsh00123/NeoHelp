# NeoHelp — Operational Task & Incident Chronology Platform

NeoHelp is an internal web application designed to replace ad-hoc chat and spreadsheet workflows for coordinating operational tasks, incident resolutions, and compliance requests across multiple teams.

The platform is designed with a **Timeline-based architecture**, prioritizing event chronology, activity history, and strict database-backed state transitions.

---

## 🛠️ Tech Stack & Constraints

- **Backend**: FastAPI (Python 3.11) with asynchronous SQLAlchemy 2.0 and PostgreSQL
- **Frontend**: React 19 + TanStack Query + Vite (Modern Vanilla CSS & Design Tokens)
- **Database**: PostgreSQL 16 (ACID transactions, row-level locks, cursor pagination)
- **Async Queue / Cache**: Redis 7 (Transactional Outbox background processing)
- **Infrastructure**: Docker Compose (Single command spin-up for Postgres, Redis, Backend, Frontend)
- **Testing**: Pytest & HTTPX async test suite

---

## 🚀 Quick Start (Docker Compose)

To spin up all services (Database, Redis, FastAPI backend, and React frontend) with a single command:

```bash
docker compose up --build
```

### Exposed Service Endpoints

| Service | Port / URL | Description |
|---|---|---|
| **Frontend** | [http://localhost:5173](http://localhost:5173) | React + Vite + TanStack Query timeline dashboard |
| **Backend API** | [http://localhost:8000](http://localhost:8000) | FastAPI core REST API |
| **Interactive Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) | Swagger UI for exploring endpoints |
| **Health Check** | [http://localhost:8000/api/health](http://localhost:8000/api/health) | Live diagnostics for API, DB, and Redis |
| **PostgreSQL** | `localhost:5432` | Relational storage (user: `postgres`, db: `neohelp`) |
| **Redis** | `localhost:6379` | In-memory queue & transactional outbox broker |

---

## 📁 Monorepo Structure

```
Neohelp/
├── docker-compose.yml          # Unified multi-service orchestration
├── .gitignore                  # Git exclusions for Python & Node
├── README.md                   # Project overview & running instructions
├── ANTIGRAVITY_MASTER_BLUEPRINT.md # Master engineering blueprint
├── Step1                       # Mission context & Phase 1 directives
├── backend/                    # FastAPI Application
│   ├── Dockerfile
│   ├── requirements.txt        # Backend dependencies
│   ├── app/
│   │   ├── main.py             # FastAPI entry point & CORS
│   │   ├── config.py           # Environment & Settings
│   │   ├── database.py         # SQLAlchemy async engine & session
│   │   └── api/
│   │       └── health.py       # Multi-service health probe
│   └── tests/
│       └── test_health.py      # Pytest API tests
└── frontend/                   # React + TanStack Query Application
    ├── Dockerfile
    ├── package.json
    ├── vite.config.js          # Vite config with API proxy
    ├── index.html              # Modern typography & SEO
    └── src/
        ├── main.jsx            # TanStack QueryClientProvider setup
        ├── App.jsx             # Timeline dashboard UI
        ├── App.css             # Theme, timeline stream, & metrics styling
        ├── index.css           # Glassmorphism design tokens & scrollbars
        └── api/
            └── client.js       # TanStack Query fetch utilities
```

---

## 🧪 Local Testing

### Backend Unit & Integration Tests:
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

### Frontend Build:
```bash
cd frontend
npm install
npm run build
```
