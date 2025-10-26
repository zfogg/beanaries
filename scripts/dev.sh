#!/bin/bash

# Start backend and frontend concurrently
trap 'kill 0' EXIT

echo "Starting Beanaries development servers..."

# Start backend
cd apps/backend
uv run python -m src.main &
BACKEND_PID=$!

# Start frontend
cd ../..
pnpm --filter @beanaries/web dev &
FRONTEND_PID=$!

echo "Backend PID: $BACKEND_PID"
echo "Frontend PID: $FRONTEND_PID"
echo ""
echo "Frontend: http://localhost:5173"
echo "Backend: http://localhost:8000"
echo "API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both servers"

wait
