import type {
  Project,
  ProjectWithStats,
  ProjectTimeseries,
  Build,
  ProjectConfig,
  LeaderboardEntry,
} from '@/types'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8001'

export async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    const errorMessage = errorData.detail || `HTTP ${response.status}: ${response.statusText}`
    throw new Error(errorMessage)
  }

  return response.json()
}

// Helper function to build query strings
function buildQueryString(params: Record<string, string | number | boolean | undefined>): string {
  const searchParams = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) {
      searchParams.set(key, value.toString())
    }
  })
  const query = searchParams.toString()
  return query ? `?${query}` : ''
}

// API Parameters Types
export interface GetProjectsParams {
  skip?: number
  limit?: number
  category?: string
  is_active?: boolean
}

export interface GetTimeseriesParams {
  platform?: string
  branch?: string
  days?: number
}

export interface GetBuildsParams {
  project_id?: number
  platform?: string
  success?: boolean
  skip?: number
  limit?: number
}

export interface GetConfigsParams {
  project_id?: number
  is_enabled?: boolean
}

export interface GetLeaderboardParams {
  platform?: string
  category?: string
  min_builds?: number
  limit?: number
}

export interface CreateProjectData {
  owner: string
  name: string
  subproject_path?: string | null
  description?: string | null
  language?: string | null
  category: string
}

export interface UpdateProjectData {
  description?: string | null
  category?: string | null
  is_active?: boolean
}

export interface CreateBuildData {
  project_id: number
  commit_sha: string
  commit_message?: string | null
  branch: string
  success: boolean
  duration_seconds?: number | null
  platform: string
  data_source: string
  workflow_name?: string | null
  workflow_run_id?: number | null
  job_id?: number | null
  build_url?: string | null
  runner?: string | null
  started_at?: string | null
  finished_at?: string | null
}

export interface CreateConfigData {
  project_id: number
  data_source: string
  platform: string
  branch?: string
  workflow_name?: string | null
  workflow_file?: string | null
  job_name?: string | null
  build_command?: string | null
  build_dir?: string | null
  source_url?: string | null
  extract_command?: string | null
  check_interval_hours?: number
}

export interface UpdateConfigData {
  data_source?: string
  platform?: string
  branch?: string
  workflow_name?: string | null
  workflow_file?: string | null
  job_name?: string | null
  build_command?: string | null
  build_dir?: string | null
  source_url?: string | null
  extract_command?: string | null
  is_enabled?: boolean
  check_interval_hours?: number
}

export const api = {
  // Projects
  getProjects: (params?: GetProjectsParams) =>
    fetchApi<Project[]>(`/projects${buildQueryString(params || {})}`),

  getProject: (id: number) => fetchApi<ProjectWithStats>(`/projects/${id}`),

  getProjectTimeseries: (id: number, params?: GetTimeseriesParams) =>
    fetchApi<ProjectTimeseries>(`/projects/${id}/timeseries${buildQueryString(params || {})}`),

  createProject: (data: CreateProjectData) =>
    fetchApi<Project>('/projects', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateProject: (id: number, data: UpdateProjectData) =>
    fetchApi<Project>(`/projects/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteProject: (id: number) =>
    fetchApi<void>(`/projects/${id}`, {
      method: 'DELETE',
    }),

  // Builds
  getBuilds: (params?: GetBuildsParams) =>
    fetchApi<Build[]>(`/builds${buildQueryString(params || {})}`),

  createBuild: (data: CreateBuildData) =>
    fetchApi<Build>('/builds', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Configs
  getConfigs: (params?: GetConfigsParams) =>
    fetchApi<ProjectConfig[]>(`/configs${buildQueryString(params || {})}`),

  createConfig: (data: CreateConfigData) =>
    fetchApi<ProjectConfig>('/configs', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateConfig: (id: number, data: UpdateConfigData) =>
    fetchApi<ProjectConfig>(`/configs/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteConfig: (id: number) =>
    fetchApi<void>(`/configs/${id}`, {
      method: 'DELETE',
    }),

  // Leaderboard
  getLeaderboard: (params?: GetLeaderboardParams) =>
    fetchApi<LeaderboardEntry[]>(`/leaderboard${buildQueryString(params || {})}`),
}
