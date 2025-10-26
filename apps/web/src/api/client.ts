const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8001'

export async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`
  console.log('fetchApi - URL:', url, 'API_BASE_URL:', API_BASE_URL)
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })

  if (!response.ok) {
    throw new Error(`API error: ${response.statusText}`)
  }

  return response.json()
}

export const api = {
  // Projects
  getProjects: (params?: {
    skip?: number
    limit?: number
    category?: string
    is_active?: boolean
  }) => {
    const searchParams = new URLSearchParams()
    if (params?.skip !== undefined) searchParams.set('skip', params.skip.toString())
    if (params?.limit !== undefined) searchParams.set('limit', params.limit.toString())
    if (params?.category) searchParams.set('category', params.category)
    if (params?.is_active !== undefined)
      searchParams.set('is_active', params.is_active.toString())

    const query = searchParams.toString()
    return fetchApi<any[]>(`/projects${query ? `?${query}` : ''}`)
  },

  getProject: (id: number) => fetchApi<any>(`/projects/${id}`),

  getProjectTimeseries: (
    id: number,
    params?: {
      platform?: string
      branch?: string
      days?: number
    }
  ) => {
    const searchParams = new URLSearchParams()
    if (params?.platform) searchParams.set('platform', params.platform)
    if (params?.branch) searchParams.set('branch', params.branch)
    if (params?.days !== undefined) searchParams.set('days', params.days.toString())

    const query = searchParams.toString()
    return fetchApi<any>(`/projects/${id}/timeseries${query ? `?${query}` : ''}`)
  },

  createProject: (data: any) =>
    fetchApi<any>('/projects', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateProject: (id: number, data: any) =>
    fetchApi<any>(`/projects/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteProject: (id: number) =>
    fetchApi<void>(`/projects/${id}`, {
      method: 'DELETE',
    }),

  // Builds
  getBuilds: (params?: {
    project_id?: number
    platform?: string
    success?: boolean
    skip?: number
    limit?: number
  }) => {
    const searchParams = new URLSearchParams()
    if (params?.project_id !== undefined)
      searchParams.set('project_id', params.project_id.toString())
    if (params?.platform) searchParams.set('platform', params.platform)
    if (params?.success !== undefined) searchParams.set('success', params.success.toString())
    if (params?.skip !== undefined) searchParams.set('skip', params.skip.toString())
    if (params?.limit !== undefined) searchParams.set('limit', params.limit.toString())

    const query = searchParams.toString()
    return fetchApi<any[]>(`/builds${query ? `?${query}` : ''}`)
  },

  createBuild: (data: any) =>
    fetchApi<any>('/builds', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Configs
  getConfigs: (params?: { project_id?: number; is_enabled?: boolean }) => {
    const searchParams = new URLSearchParams()
    if (params?.project_id !== undefined)
      searchParams.set('project_id', params.project_id.toString())
    if (params?.is_enabled !== undefined)
      searchParams.set('is_enabled', params.is_enabled.toString())

    const query = searchParams.toString()
    return fetchApi<any[]>(`/configs${query ? `?${query}` : ''}`)
  },

  createConfig: (data: any) =>
    fetchApi<any>('/configs', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateConfig: (id: number, data: any) =>
    fetchApi<any>(`/configs/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteConfig: (id: number) =>
    fetchApi<void>(`/configs/${id}`, {
      method: 'DELETE',
    }),

  // Leaderboard
  getLeaderboard: (params?: {
    platform?: string
    category?: string
    min_builds?: number
    limit?: number
  }) => {
    const searchParams = new URLSearchParams()
    if (params?.platform) searchParams.set('platform', params.platform)
    if (params?.category) searchParams.set('category', params.category)
    if (params?.min_builds !== undefined)
      searchParams.set('min_builds', params.min_builds.toString())
    if (params?.limit !== undefined) searchParams.set('limit', params.limit.toString())

    const query = searchParams.toString()
    return fetchApi<any[]>(`/leaderboard${query ? `?${query}` : ''}`)
  },
}
