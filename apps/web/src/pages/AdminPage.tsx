import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { Project, ProjectConfig, DataSource, Platform, ProjectCategory } from '@/types'

interface ProjectFormData {
  owner: string
  name: string
  git_url: string
  subproject_path: string
  description: string
  language: string
  category: ProjectCategory
  // Configuration
  configType: 'github_actions' | 'local_build' | 'both'
  sourceType: 'git' | 'direct_download'
  github_actions_workflow: string
  github_actions_job: string
  build_command: string
  build_dir: string
  source_url: string
  extract_command: string
  platforms: Platform[]
  branch: string
  check_interval_hours: number
}

export default function AdminPage() {
  const queryClient = useQueryClient()
  const [showAddProject, setShowAddProject] = useState(false)
  const [selectedProject, setSelectedProject] = useState<number | null>(null)

  const [formData, setFormData] = useState<ProjectFormData>({
    owner: '',
    name: '',
    git_url: '',
    subproject_path: '',
    description: '',
    language: '',
    category: ProjectCategory.OTHER,
    configType: 'github_actions',
    sourceType: 'git',
    github_actions_workflow: '',
    github_actions_job: '',
    build_command: '',
    build_dir: '',
    source_url: '',
    extract_command: '',
    platforms: [Platform.UBUNTU_LATEST],
    branch: 'main',
    check_interval_hours: 24,
  })

  const { data: projects, isLoading, error } = useQuery<Project[]>({
    queryKey: ['projects'],
    queryFn: () => api.getProjects({ limit: 100 }),
  })

  console.log('AdminPage - projects:', projects, 'isLoading:', isLoading, 'error:', error)

  const { data: configs } = useQuery<ProjectConfig[]>({
    queryKey: ['configs', selectedProject],
    queryFn: () => api.getConfigs({ project_id: selectedProject || undefined }),
    enabled: !!selectedProject,
  })

  const createProjectMutation = useMutation({
    mutationFn: async (data: ProjectFormData) => {
      const payload: any = {
        owner: data.owner,
        name: data.name,
        git_url: data.git_url || undefined,
        subproject_path: data.subproject_path || undefined,
        description: data.description || undefined,
        language: data.language || undefined,
        category: data.category,
        platforms: data.platforms,
        branch: data.branch,
        check_interval_hours: data.check_interval_hours,
      }

      // Add GitHub Actions config if selected
      if (data.configType === 'github_actions' || data.configType === 'both') {
        if (data.github_actions_workflow) {
          payload.github_actions_workflow = data.github_actions_workflow
          if (data.github_actions_job) {
            payload.github_actions_job = data.github_actions_job
          }
        }
      }

      // Add local build config if selected
      if (data.configType === 'local_build' || data.configType === 'both') {
        if (data.build_command) {
          payload.build_command = data.build_command
          if (data.build_dir) {
            payload.build_dir = data.build_dir
          }

          // Add source download config if direct download
          if (data.sourceType === 'direct_download') {
            if (data.source_url) {
              payload.source_url = data.source_url
            }
            if (data.extract_command) {
              payload.extract_command = data.extract_command
            }
          }
        }
      }

      const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8001'
      const response = await fetch(`${API_BASE_URL}/projects/with-config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || 'Failed to create project')
      }

      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      setShowAddProject(false)
      // Reset form
      setFormData({
        owner: '',
        name: '',
        git_url: '',
        subproject_path: '',
        description: '',
        language: '',
        category: ProjectCategory.OTHER,
        configType: 'github_actions',
        sourceType: 'git',
        github_actions_workflow: '',
        github_actions_job: '',
        build_command: '',
        build_dir: '',
        source_url: '',
        extract_command: '',
        platforms: [Platform.UBUNTU_LATEST],
        branch: 'main',
        check_interval_hours: 24,
      })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createProjectMutation.mutate(formData)
  }

  const togglePlatform = (platform: Platform) => {
    setFormData((prev) => ({
      ...prev,
      platforms: prev.platforms.includes(platform)
        ? prev.platforms.filter((p) => p !== platform)
        : [...prev.platforms, platform],
    }))
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Admin Dashboard</h1>
        <button
          onClick={() => setShowAddProject(true)}
          className="btn btn-primary"
        >
          Add Project
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="card p-6">
          <h2 className="text-xl font-bold text-gray-900 mb-4">
            Projects ({projects?.length || 0})
          </h2>
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {projects?.map((project) => (
              <div
                key={project.id}
                onClick={() => setSelectedProject(project.id)}
                className={`p-3 rounded-lg cursor-pointer transition ${
                  selectedProject === project.id
                    ? 'bg-primary-50 border-2 border-primary-500'
                    : 'bg-gray-50 hover:bg-gray-100'
                }`}
              >
                <p className="font-semibold text-gray-900">
                  {project.full_name}
                  {project.subproject_path && (
                    <span className="ml-2 text-xs font-mono text-primary-600 bg-primary-100 px-2 py-0.5 rounded">
                      {project.subproject_path}
                    </span>
                  )}
                </p>
                <p className="text-sm text-gray-600">{project.category.replace('_', ' ')}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="card p-6">
          <h2 className="text-xl font-bold text-gray-900 mb-4">
            {selectedProject ? 'Configurations' : 'Select a project'}
          </h2>
          {selectedProject && (
            <div className="space-y-3">
              {configs?.map((config) => (
                <div key={config.id} className="p-4 bg-gray-50 rounded-lg">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-semibold text-gray-900">
                      {config.data_source.replace('_', ' ')}
                    </span>
                    <span
                      className={`px-2 py-1 text-xs rounded ${
                        config.is_enabled
                          ? 'bg-green-100 text-green-800'
                          : 'bg-gray-200 text-gray-600'
                      }`}
                    >
                      {config.is_enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </div>
                  <div className="text-sm text-gray-600 space-y-1">
                    <p>Platform: {config.platform}</p>
                    <p>Branch: {config.branch}</p>
                    {config.workflow_file && <p>Workflow: {config.workflow_file}</p>}
                    {config.job_name && <p>Job: {config.job_name}</p>}
                    {config.build_command && (
                      <p className="font-mono text-xs">Build: {config.build_command}</p>
                    )}
                    {config.build_dir && <p>Build dir: {config.build_dir}</p>}
                    <p className="text-xs text-gray-500">
                      Check every {config.check_interval_hours}h
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {showAddProject && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="card p-6 max-w-3xl w-full max-h-[90vh] overflow-y-auto">
            <h2 className="text-2xl font-bold text-gray-900 mb-6">
              Add Project with Configuration
            </h2>

            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Basic Info */}
              <div className="border-b pb-4">
                <h3 className="text-lg font-semibold mb-3">Project Information</h3>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Owner *
                    </label>
                    <input
                      type="text"
                      value={formData.owner}
                      onChange={(e) => setFormData({ ...formData, owner: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                      placeholder="rust-lang"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Repository Name *
                    </label>
                    <input
                      type="text"
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                      placeholder="rust"
                      required
                    />
                  </div>
                  <div className="col-span-2">
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Git URL (optional)
                    </label>
                    <input
                      type="text"
                      value={formData.git_url}
                      onChange={(e) =>
                        setFormData({ ...formData, git_url: e.target.value })
                      }
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg font-mono text-sm"
                      placeholder="https://git.savannah.gnu.org/git/gcc.git or leave empty for GitHub"
                    />
                    <p className="text-xs text-gray-500 mt-1">
                      For non-GitHub git repos, provide the full git URL. Leave empty to use GitHub (owner/name)
                    </p>
                  </div>
                  <div className="col-span-2">
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Subproject Path (optional)
                    </label>
                    <input
                      type="text"
                      value={formData.subproject_path}
                      onChange={(e) =>
                        setFormData({ ...formData, subproject_path: e.target.value })
                      }
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg font-mono text-sm"
                      placeholder="llvm/ or clang/ or leave empty for non-monorepos"
                    />
                    <p className="text-xs text-gray-500 mt-1">
                      For monorepos like llvm/llvm-project, specify the subproject directory (e.g., 'llvm/', 'clang/', 'lld/')
                    </p>
                  </div>
                  <div className="col-span-2">
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Description
                    </label>
                    <input
                      type="text"
                      value={formData.description}
                      onChange={(e) =>
                        setFormData({ ...formData, description: e.target.value })
                      }
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                      placeholder="A language empowering everyone..."
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Language
                    </label>
                    <input
                      type="text"
                      value={formData.language}
                      onChange={(e) => setFormData({ ...formData, language: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                      placeholder="Rust"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Category *
                    </label>
                    <select
                      value={formData.category}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          category: e.target.value as ProjectCategory,
                        })
                      }
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    >
                      {Object.values(ProjectCategory).map((cat) => (
                        <option key={cat} value={cat}>
                          {cat.replace('_', ' ')}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              {/* Configuration Type */}
              <div className="border-b pb-4">
                <h3 className="text-lg font-semibold mb-3">Data Collection Method</h3>
                <div className="space-y-2">
                  <label className="flex items-center space-x-3">
                    <input
                      type="radio"
                      name="configType"
                      value="github_actions"
                      checked={formData.configType === 'github_actions'}
                      onChange={(e) =>
                        setFormData({ ...formData, configType: e.target.value as any })
                      }
                      className="w-4 h-4"
                    />
                    <span className="font-medium">GitHub Actions Only</span>
                    <span className="text-sm text-gray-500">
                      Scrape build times from GitHub Actions
                    </span>
                  </label>
                  <label className="flex items-center space-x-3">
                    <input
                      type="radio"
                      name="configType"
                      value="local_build"
                      checked={formData.configType === 'local_build'}
                      onChange={(e) =>
                        setFormData({ ...formData, configType: e.target.value as any })
                      }
                      className="w-4 h-4"
                    />
                    <span className="font-medium">Local Build Only</span>
                    <span className="text-sm text-gray-500">
                      Build locally to measure compile time
                    </span>
                  </label>
                  <label className="flex items-center space-x-3">
                    <input
                      type="radio"
                      name="configType"
                      value="both"
                      checked={formData.configType === 'both'}
                      onChange={(e) =>
                        setFormData({ ...formData, configType: e.target.value as any })
                      }
                      className="w-4 h-4"
                    />
                    <span className="font-medium">Both</span>
                    <span className="text-sm text-gray-500">
                      Track both GitHub Actions and local builds
                    </span>
                  </label>
                </div>
              </div>

              {/* GitHub Actions Config */}
              {(formData.configType === 'github_actions' || formData.configType === 'both') && (
                <div className="border-b pb-4">
                  <h3 className="text-lg font-semibold mb-3">GitHub Actions Configuration</h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Workflow File *
                      </label>
                      <input
                        type="text"
                        value={formData.github_actions_workflow}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            github_actions_workflow: e.target.value,
                          })
                        }
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                        placeholder="ci.yml"
                        required={formData.configType !== 'local_build'}
                      />
                      <p className="text-xs text-gray-500 mt-1">
                        The workflow file name (e.g., ci.yml, build.yml)
                      </p>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Job Name (optional)
                      </label>
                      <input
                        type="text"
                        value={formData.github_actions_job}
                        onChange={(e) =>
                          setFormData({ ...formData, github_actions_job: e.target.value })
                        }
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                        placeholder="build"
                      />
                      <p className="text-xs text-gray-500 mt-1">
                        Specific job to track (leave empty for all)
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Local Build Config */}
              {(formData.configType === 'local_build' || formData.configType === 'both') && (
                <div className="border-b pb-4">
                  <h3 className="text-lg font-semibold mb-3">Local Build Configuration</h3>
                  <div className="space-y-4">
                    {/* Source Type */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Source Type
                      </label>
                      <div className="space-y-2">
                        <label className="flex items-center space-x-3">
                          <input
                            type="radio"
                            name="sourceType"
                            value="git"
                            checked={formData.sourceType === 'git'}
                            onChange={(e) =>
                              setFormData({ ...formData, sourceType: e.target.value as any })
                            }
                            className="w-4 h-4"
                          />
                          <span className="font-medium">Git Clone</span>
                          <span className="text-sm text-gray-500">
                            Clone from git repository
                          </span>
                        </label>
                        <label className="flex items-center space-x-3">
                          <input
                            type="radio"
                            name="sourceType"
                            value="direct_download"
                            checked={formData.sourceType === 'direct_download'}
                            onChange={(e) =>
                              setFormData({ ...formData, sourceType: e.target.value as any })
                            }
                            className="w-4 h-4"
                          />
                          <span className="font-medium">Direct Download</span>
                          <span className="text-sm text-gray-500">
                            Download and extract source archive (wget + tar/unzip)
                          </span>
                        </label>
                      </div>
                    </div>

                    {/* Direct Download Fields */}
                    {formData.sourceType === 'direct_download' && (
                      <>
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">
                            Source URL *
                          </label>
                          <input
                            type="text"
                            value={formData.source_url}
                            onChange={(e) =>
                              setFormData({ ...formData, source_url: e.target.value })
                            }
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg font-mono text-sm"
                            placeholder="https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.6.1.tar.xz"
                            required={formData.sourceType === 'direct_download'}
                          />
                          <p className="text-xs text-gray-500 mt-1">
                            Direct URL to download source archive
                          </p>
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">
                            Extract Command *
                          </label>
                          <input
                            type="text"
                            value={formData.extract_command}
                            onChange={(e) =>
                              setFormData({ ...formData, extract_command: e.target.value })
                            }
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg font-mono text-sm"
                            placeholder="tar -xJf"
                            required={formData.sourceType === 'direct_download'}
                          />
                          <p className="text-xs text-gray-500 mt-1">
                            Command to extract the archive (e.g., "tar -xzf", "tar -xJf", "unzip")
                          </p>
                        </div>
                      </>
                    )}

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Build Command *
                      </label>
                      <input
                        type="text"
                        value={formData.build_command}
                        onChange={(e) =>
                          setFormData({ ...formData, build_command: e.target.value })
                        }
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg font-mono text-sm"
                        placeholder="python3 x.py build"
                        required={formData.configType !== 'github_actions'}
                      />
                      <p className="text-xs text-gray-500 mt-1">
                        The command to build the project
                      </p>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Build Directory (optional)
                      </label>
                      <input
                        type="text"
                        value={formData.build_dir}
                        onChange={(e) =>
                          setFormData({ ...formData, build_dir: e.target.value })
                        }
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg font-mono text-sm"
                        placeholder="src/"
                      />
                      <p className="text-xs text-gray-500 mt-1">
                        Directory to run build in (relative to repo root)
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Common Settings */}
              <div className="border-b pb-4">
                <h3 className="text-lg font-semibold mb-3">Common Settings</h3>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Platforms *
                    </label>
                    <div className="grid grid-cols-3 gap-2">
                      {Object.values(Platform).map((platform) => (
                        <label
                          key={platform}
                          className="flex items-center space-x-2 p-2 border rounded cursor-pointer hover:bg-gray-50"
                        >
                          <input
                            type="checkbox"
                            checked={formData.platforms.includes(platform)}
                            onChange={() => togglePlatform(platform)}
                            className="w-4 h-4"
                          />
                          <span className="text-sm">{platform}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Branch
                      </label>
                      <input
                        type="text"
                        value={formData.branch}
                        onChange={(e) =>
                          setFormData({ ...formData, branch: e.target.value })
                        }
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                        placeholder="main"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Check Interval (hours)
                      </label>
                      <input
                        type="number"
                        value={formData.check_interval_hours}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            check_interval_hours: parseInt(e.target.value),
                          })
                        }
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                        min="1"
                        max="168"
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* Submit */}
              <div className="flex space-x-3">
                <button
                  type="submit"
                  disabled={createProjectMutation.isPending}
                  className="flex-1 btn btn-primary disabled:opacity-50"
                >
                  {createProjectMutation.isPending ? 'Creating...' : 'Create Project'}
                </button>
                <button
                  type="button"
                  onClick={() => setShowAddProject(false)}
                  className="flex-1 btn btn-secondary"
                >
                  Cancel
                </button>
              </div>

              {createProjectMutation.isError && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                  Error: {createProjectMutation.error.message}
                </div>
              )}
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
