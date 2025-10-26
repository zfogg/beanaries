# Beanaries Frontend

React frontend for the build time leaderboard.

## Development

```bash
# Install dependencies
pnpm install

# Start dev server
pnpm dev

# Build for production
pnpm build

# Preview production build
pnpm preview
```

## Environment Variables

Create a `.env.local` file:

```env
VITE_API_URL=http://localhost:8000
```

## Features

- Leaderboard view with filtering by platform and category
- Individual project pages with build time charts
- Admin dashboard for managing projects and configurations
- Responsive design with Tailwind CSS
- Real-time data updates with React Query

## Components

- `Layout` - Main layout with header and footer
- `LeaderboardCard` - Individual project card on the leaderboard
- `BuildTimeChart` - Recharts line/scatter chart for build times
- `HomePage` - Main leaderboard page
- `ProjectPage` - Individual project details
- `AdminPage` - Admin dashboard

## Tech Stack

- React 18
- TypeScript
- Vite
- TanStack Query
- Tailwind CSS
- Recharts
- React Router
