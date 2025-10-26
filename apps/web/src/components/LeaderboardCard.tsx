import { Link } from 'react-router-dom'
import { LeaderboardEntry } from '@/types'
import { formatDuration, formatNumber, formatPercent } from '@/utils/format'

interface LeaderboardCardProps {
  entry: LeaderboardEntry
  rank: number
}

export default function LeaderboardCard({ entry, rank }: LeaderboardCardProps) {
  const { project, avg_build_time_seconds, latest_build_time_seconds, success_rate, total_builds } = entry

  const getRankEmoji = (rank: number) => {
    if (rank === 1) return '🥇'
    if (rank === 2) return '🥈'
    if (rank === 3) return '🥉'
    return `#${rank}`
  }

  const getChangeIndicator = () => {
    if (!avg_build_time_seconds || !latest_build_time_seconds) return null
    const diff = latest_build_time_seconds - avg_build_time_seconds
    if (Math.abs(diff) < 60) return null // Less than 1 minute difference

    const isIncrease = diff > 0
    return (
      <span className={`text-sm ${isIncrease ? 'text-red-600' : 'text-green-600'}`}>
        {isIncrease ? '↑' : '↓'} {formatDuration(Math.abs(diff))}
      </span>
    )
  }

  return (
    <Link to={`/project/${project.id}`} className="block">
      <div className="card p-6 hover:shadow-md transition-shadow">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center space-x-3 mb-2">
              <span className="text-2xl">{getRankEmoji(rank)}</span>
              <div>
                <h3 className="text-lg font-semibold text-gray-900">
                  {project.full_name}
                  {project.subproject_path && (
                    <span className="text-gray-500 font-normal"> / {project.subproject_path}</span>
                  )}
                </h3>
                {project.description && (
                  <p className="text-sm text-gray-600 line-clamp-1">{project.description}</p>
                )}
              </div>
            </div>

            <div className="flex items-center space-x-4 mt-3">
              <div>
                <p className="text-sm text-gray-500">Average Build Time</p>
                <p className="text-xl font-bold text-primary-600">
                  {formatDuration(avg_build_time_seconds || 0)}
                </p>
              </div>

              {getChangeIndicator() && (
                <div>
                  <p className="text-sm text-gray-500">vs Latest</p>
                  {getChangeIndicator()}
                </div>
              )}
            </div>
          </div>

          <div className="text-right">
            <div className="flex items-center space-x-2 text-sm text-gray-500 mb-2">
              <span>⭐ {formatNumber(project.stars)}</span>
              {project.language && (
                <span className="px-2 py-1 bg-gray-100 rounded">{project.language}</span>
              )}
            </div>
            <div className="text-sm text-gray-600">
              <p>Success Rate: {formatPercent(success_rate)}</p>
              <p>{total_builds} builds tracked</p>
            </div>
          </div>
        </div>
      </div>
    </Link>
  )
}
