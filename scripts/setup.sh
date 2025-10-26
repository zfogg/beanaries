#!/bin/bash

echo "Setting up Beanaries..."

# Check for required tools
command -v node >/dev/null 2>&1 || { echo "Error: Node.js is required but not installed." >&2; exit 1; }
command -v pnpm >/dev/null 2>&1 || { echo "Error: pnpm is required. Run 'corepack enable' first." >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "Error: Docker is required but not installed." >&2; exit 1; }
command -v uv >/dev/null 2>&1 || { echo "Error: uv is required. Install with 'pip install uv'." >&2; exit 1; }

echo "✓ All required tools found"

# Install frontend dependencies
echo "Installing frontend dependencies..."
pnpm install

# Install backend dependencies
echo "Installing backend dependencies..."
cd apps/backend
uv sync
cd ../..

# Setup environment files
if [ ! -f apps/backend/.env ]; then
    echo "Creating backend .env file..."
    cp apps/backend/.env.example apps/backend/.env
fi

if [ ! -f apps/web/.env.local ]; then
    echo "Creating frontend .env.local file..."
    cp apps/web/.env.example apps/web/.env.local
fi

# Start database
echo "Starting PostgreSQL and Redis..."
docker compose up -d

# Wait for database to be ready
echo "Waiting for database to be ready..."
sleep 5

echo ""
echo "✓ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit apps/backend/.env with your GitHub token"
echo "2. Run 'pnpm dev' to start both frontend and backend"
echo "3. Visit http://localhost:5173 for the frontend"
echo "4. Visit http://localhost:8000/docs for API documentation"
