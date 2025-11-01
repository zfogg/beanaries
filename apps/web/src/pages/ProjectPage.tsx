import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { ProjectWithStats, ProjectTimeseries, Platform } from '@/types'
import BuildTimeChart from '@/components/BuildTimeChart'
import { formatDuration, formatNumber, formatPercent } from '@/utils/format'
import { format } from 'date-fns'

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>()
  const [platform, setPlatform] = useState<string>('')

  // Helper function to determine source button text based on URL
  const getSourceButtonText = (url: string) => {
    if (url.includes('github.com')) return 'View on GitHub'
    if (url.includes('gitlab')) return 'View on GitLab'
    if (url.includes('googlesource.com')) return 'View on Google Git'
    if (url.includes('git.')) return 'View Repository'
    return 'View Source Code'
  }

  const { data: project, isLoading: projectLoading } = useQuery<ProjectWithStats>({
    queryKey: ['project', id],
    queryFn: () => api.getProject(Number(id)),
    enabled: !!id,
  })

  const { data: timeseries, isLoading: timeseriesLoading } = useQuery<ProjectTimeseries>({
    queryKey: ['timeseries', id, platform],
    queryFn: () =>
      api.getProjectTimeseries(Number(id), {
        platform: platform || undefined,
        days: 90,
      }),
    enabled: !!id,
  })

  if (projectLoading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="text-center py-12">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-primary-600 border-r-transparent"></div>
          <p className="mt-4 text-gray-600">Loading project...</p>
        </div>
      </div>
    )
  }

  if (!project) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="text-center py-12">
          <h2 className="text-2xl font-bold text-gray-900">Project not found</h2>
          <Link to="/" className="text-primary-600 hover:text-primary-700 mt-4 inline-block">
            Back to leaderboard
          </Link>
        </div>
      </div>
    )
  }

  const { stats } = project
  const successRate = stats.total_builds > 0
    ? (stats.successful_builds / stats.total_builds) * 100
    : 0

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <Link to="/" className="text-primary-600 hover:text-primary-700 mb-4 inline-block">
        ← Back to leaderboard
      </Link>

      <div className="card p-6 mb-8">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">
              {project.full_name}
              {project.subproject_path && (
                <span className="text-gray-500 font-normal"> / {project.subproject_path}</span>
              )}
            </h1>
            {project.description && (
              <p className="text-gray-600">{project.description}</p>
            )}
          </div>
          <a
            href={project.url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-primary"
          >
            {getSourceButtonText(project.url)}
          </a>
        </div>

        <div className="flex items-center space-x-4 text-sm text-gray-600">
          <span>⭐ {formatNumber(project.stars)} stars</span>
          {project.language && <span>• {project.language}</span>}
          <span>• {project.category.replace('_', ' ')}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <div className="card p-4">
          <p className="text-sm text-gray-500 mb-1">Average Build Time</p>
          <p className="text-2xl font-bold text-primary-600">
            {formatDuration(stats.avg_duration_seconds || 0)}
          </p>
        </div>
        <div className="card p-4">
          <p className="text-sm text-gray-500 mb-1">Latest Build</p>
          <p className="text-2xl font-bold text-gray-900">
            {formatDuration(stats.latest_build?.duration_seconds || 0)}
          </p>
        </div>
        <div className="card p-4">
          <p className="text-sm text-gray-500 mb-1">Success Rate</p>
          <p className="text-2xl font-bold text-green-600">{formatPercent(successRate)}</p>
        </div>
        <div className="card p-4">
          <p className="text-sm text-gray-500 mb-1">Total Builds</p>
          <p className="text-2xl font-bold text-gray-900">{stats.total_builds}</p>
        </div>
      </div>

      <div className="card p-6 mb-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-gray-900">Build Time History</h2>
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

        {timeseriesLoading ? (
          <div className="text-center py-12">
            <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-primary-600 border-r-transparent"></div>
          </div>
        ) : timeseries && timeseries.points.length > 0 ? (
          <BuildTimeChart data={timeseries.points} />
        ) : (
          <p className="text-center text-gray-500 py-12">No build data available</p>
        )}
      </div>

      <div className="card p-6">
        <h2 className="text-xl font-bold text-gray-900 mb-4">Recent Builds</h2>
        <div className="space-y-3">
          {project.latest_builds
            .filter((build) => build.duration_seconds !== null && build.duration_seconds >= 0)
            .map((build) => {
              const content = (
                <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg gap-4">
                  <div className="flex items-center space-x-3 flex-1 min-w-0">
                    <span
                      className={`w-3 h-3 rounded-full flex-shrink-0 ${
                        build.success ? 'bg-green-500' : 'bg-red-500'
                      }`}
                    ></span>
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-gray-900">
                        {build.commit_sha.substring(0, 7)}
                      </p>
                      {build.commit_message && (
                        <p className="text-sm text-gray-600 truncate">
                          {build.commit_message}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="font-semibold text-gray-900">
                      {formatDuration(build.duration_seconds)}
                    </p>
                    <p className="text-sm text-gray-500 whitespace-nowrap">
                      {format(new Date(build.finished_at || build.created_at), 'PPp')}
                    </p>
                  </div>
                </div>
              )

              return build.build_url ? (
                <a
                  key={build.id}
                  href={build.build_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block hover:opacity-80 transition-opacity"
                >
                  {content}
                </a>
              ) : (
                <div key={build.id}>{content}</div>
              )
            })}
        </div>
      </div>
    </div>
  )
}
