# Quick Start Guide

## Prerequisites

1. Install required tools:
   - Python 3.11+ with `uv` package manager: `pip install uv`
   - Node.js 20+
   - Docker Desktop (for PostgreSQL)
   - Enable Corepack: `corepack enable`

## Setup (5 minutes)

### Option A: Automatic Setup (Linux/Mac)

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

### Option B: Manual Setup (Windows/Any)

```bash
# 1. Install frontend dependencies
pnpm install

# 2. Install backend dependencies
cd apps/backend
uv sync
cd ../..

# 3. Start database
docker compose up -d

# 4. Setup environment files
cp apps/backend/.env.example apps/backend/.env
cp apps/web/.env.example apps/web/.env.local

# 5. Add your GitHub token to apps/backend/.env (optional but recommended)
# GITHUB_TOKEN=your_token_here
```

## Running the Application

### Development Mode

Start both frontend and backend:

```bash
pnpm dev
```

Or manually:

```bash
# Terminal 1: Backend
cd apps/backend
uv run python -m src.main

# Terminal 2: Frontend
pnpm --filter @beanaries/web dev
```

Access the application:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## Initial Data Setup

### 1. Initialize Database

```bash
cd apps/backend
uv run python -m src.cli init-db
```

### 2. Add Your First Project

Via API:
```bash
curl -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "torvalds",
    "name": "linux",
    "category": "kernel",
    "language": "C"
  }'
```

Or use the admin dashboard at http://localhost:5173/admin

### 3. Configure Data Collection

Add a GitHub Actions configuration:
```bash
curl -X POST http://localhost:8000/configs \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": 1,
    "data_source": "github_actions",
    "platform": "ubuntu-latest",
    "workflow_file": "build.yml",
    "branch": "main"
  }'
```

### 4. Run Scrapers

```bash
cd apps/backend

# Scrape GitHub Actions
uv run python -m src.cli scrape

# Or run local builds (if configured)
uv run python -m src.cli build

# List all projects
uv run python -m src.cli list
```

## Example Projects to Track

Here are some popular projects you can add:

```bash
# LLVM/Clang
curl -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -d '{"owner": "llvm", "name": "llvm-project", "category": "compiler"}'

# Chromium (via chromium/chromium mirror)
curl -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -d '{"owner": "chromium", "name": "chromium", "category": "browser"}'

# Rust
curl -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -d '{"owner": "rust-lang", "name": "rust", "category": "compiler"}'

# PyTorch
curl -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -d '{"owner": "pytorch", "name": "pytorch", "category": "ml_framework"}'

# TensorFlow
curl -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -d '{"owner": "tensorflow", "name": "tensorflow", "category": "ml_framework"}'
```

## Useful Commands

```bash
# Backend CLI
cd apps/backend

uv run python -m src.cli scrape    # Scrape GitHub Actions
uv run python -m src.cli build     # Run local builds
uv run python -m src.cli list      # List projects
uv run python -m src.cli init-db   # Initialize database

# Frontend
pnpm --filter @beanaries/web dev   # Start dev server
pnpm --filter @beanaries/web build # Production build

# Database
docker compose up -d               # Start database
docker compose down                # Stop database
docker compose logs -f postgres    # View logs
```

## Troubleshooting

### Database connection errors
```bash
# Check if database is running
docker compose ps

# Restart database
docker compose restart postgres

# Check logs
docker compose logs postgres
```

### Port already in use
```bash
# Backend (port 8000)
# Kill existing process or change API_PORT in apps/backend/.env

# Frontend (port 5173)
# Vite will automatically use next available port

# Database (port 5432)
# Change port in docker-compose.yml
```

### Missing dependencies
```bash
# Frontend
pnpm install

# Backend
cd apps/backend
uv sync
```

## Next Steps

1. Add ~10-20 projects via the admin dashboard
2. Configure GitHub Actions scraping for each project
3. Run the scraper: `uv run python -m src.cli scrape`
4. View the leaderboard at http://localhost:5173
5. Check individual project pages for build time trends
6. Set up a cron job to run the scraper regularly

## Production Deployment

See README.md for production deployment instructions including:
- Environment variable configuration
- Database migrations with Alembic
- Reverse proxy setup
- Process management
- Monitoring and logging
