import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { LeaderboardEntry, Platform, ProjectCategory } from '@/types'
import LeaderboardCard from '@/components/LeaderboardCard'

export default function HomePage() {
  const [platform, setPlatform] = useState<string>('')
  const [category, setCategory] = useState<string>('')

  const { data: leaderboard, isLoading } = useQuery<LeaderboardEntry[]>({
    queryKey: ['leaderboard', platform, category],
    queryFn: () =>
      api.getLeaderboard({
        platform: platform || undefined,
        category: category || undefined,
        limit: 100,
      }),
  })

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">
          Build Time Leaderboard
        </h1>
        <p className="text-lg text-gray-600">
          How long does it REALLY take to compile popular open source projects?
        </p>
      </div>

      <div className="flex flex-wrap gap-4 mb-8">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Platform
          </label>
          <select
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
            className="px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <option value="">All Platforms</option>
            {Object.values(Platform).map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Category
          </label>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <option value="">All Categories</option>
            {Object.values(ProjectCategory).map((c) => (
              <option key={c} value={c}>
                {c.replace('_', ' ')}
              </option>
            ))}
          </select>
        </div>
      </div>

      {isLoading ? (
        <div className="text-center py-12">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-primary-600 border-r-transparent"></div>
          <p className="mt-4 text-gray-600">Loading leaderboard...</p>
        </div>
      ) : (
        <div className="space-y-4">
          {leaderboard && leaderboard.length > 0 ? (
            leaderboard.map((entry, index) => (
              <LeaderboardCard key={entry.project.id} entry={entry} rank={index + 1} />
            ))
          ) : (
            <div className="text-center py-12 text-gray-500">
              No projects found. Try adjusting your filters.
            </div>
          )}
        </div>
      )}
    </div>
  )
}
