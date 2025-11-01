export enum ProjectCategory {
  COMPILER = 'compiler',
  KERNEL = 'kernel',
  BROWSER = 'browser',
  ML_FRAMEWORK = 'ml_framework',
  LANGUAGE_RUNTIME = 'language_runtime',
  DATABASE = 'database',
  WEB_FRAMEWORK = 'web_framework',
  BUILD_TOOL = 'build_tool',
  GRAPHICS = 'graphics',
  MEDIA = 'media',
  DEVTOOLS = 'devtools',
  INFRASTRUCTURE = 'infrastructure',
  OTHER = 'other',
}

export enum Platform {
  UBUNTU_LATEST = 'ubuntu-latest',
  MACOS_LATEST = 'macos-latest',
  WINDOWS_LATEST = 'windows-latest',
  UBUNTU_22_04 = 'ubuntu-22.04',
  UBUNTU_24_04 = 'ubuntu-24.04',
  MACOS_13 = 'macos-13',
  MACOS_14 = 'macos-14',
  WINDOWS_2022 = 'windows-2022',
}

export enum DataSource {
  GITHUB_ACTIONS = 'github_actions',
  BUILDKITE = 'buildkite',
  LUCI = 'luci',
  GITLAB_CI = 'gitlab_ci',
  LOCAL_BUILD = 'local_build',
  MANUAL = 'manual',
}

export interface Project {
  id: number
  owner: string
  name: string
  full_name: string
  url: string
  subproject_path: string | null
  description: string | null
  stars: number
  language: string | null
  category: ProjectCategory
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Build {
  id: number
  project_id: number
  commit_sha: string
  commit_message: string | null
  branch: string
  success: boolean
  duration_seconds: number | null
  platform: Platform
  data_source: DataSource
  workflow_name: string | null
  workflow_run_id: number | null
  job_id: number | null
  build_url: string | null
  runner: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}

export interface BuildStats {
  total_builds: number
  successful_builds: number
  failed_builds: number
  avg_duration_seconds: number | null
  min_duration_seconds: number | null
  max_duration_seconds: number | null
  latest_build: Build | null
}

export interface ProjectWithStats extends Project {
  stats: BuildStats
  latest_builds: Build[]
}

export interface TimeseriesPoint {
  timestamp: string
  duration_seconds: number | null
  success: boolean
  commit_sha: string
  commit_message?: string | null
  build_url?: string | null
}

export interface ProjectTimeseries {
  project_id: number
  project_name: string
  platform: string
  points: TimeseriesPoint[]
}

export interface LeaderboardEntry {
  project: Project
  avg_build_time_seconds: number | null
  latest_build_time_seconds: number | null
  success_rate: number
  total_builds: number
}

export interface ProjectConfig {
  id: number
  project_id: number
  data_source: DataSource
  platform: Platform
  branch: string
  workflow_name: string | null
  workflow_file: string | null
  job_name: string | null
  build_command: string | null
  build_dir: string | null
  source_url: string | null
  extract_command: string | null
  is_enabled: boolean
  check_interval_hours: number
  last_checked_at: string | null
  created_at: string
  updated_at: string
}
