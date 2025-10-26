# Beanaries Backend

FastAPI backend for tracking build times of open source projects.

## Development

### Setup

```bash
# Install uv if you haven't
pip install uv

# Install dependencies
uv sync

# Start database
docker compose up -d

# Copy environment variables
cp .env.example .env

# Run the server
uv run python -m src.main
```

### API Documentation

Visit `http://localhost:8000/docs` for interactive API documentation.

### Database Migrations

This project uses Alembic for database migrations:

```bash
# Create a new migration
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head

# Rollback
uv run alembic downgrade -1
```

### Running Scrapers

```bash
# Scrape GitHub Actions
uv run python -m src.scrapers.github_actions

# Run local builds
uv run python -m src.scrapers.local_builder
```

## API Endpoints

### Projects
- `GET /projects` - List all projects
- `POST /projects` - Create a project
- `GET /projects/{id}` - Get project details with stats
- `PATCH /projects/{id}` - Update a project
- `DELETE /projects/{id}` - Delete a project
- `GET /projects/{id}/timeseries` - Get build time history

### Builds
- `GET /builds` - List builds
- `POST /builds` - Create a build record
- `GET /builds/{id}` - Get build details
- `DELETE /builds/{id}` - Delete a build

### Configurations
- `GET /configs` - List project configurations
- `POST /configs` - Create a configuration
- `GET /configs/{id}` - Get configuration
- `PATCH /configs/{id}` - Update a configuration
- `DELETE /configs/{id}` - Delete a configuration

### Leaderboard
- `GET /leaderboard` - Get the leaderboard

## Testing

```bash
# Run tests
uv run pytest

# With coverage
uv run pytest --cov=src
```
