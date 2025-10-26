# Adding Projects to Beanaries

This guide shows you how to add projects with complete build/scrape configuration in one request.

## Endpoint: `POST /projects/with-config`

This endpoint allows you to create a project and configure how to track its build times in a single request.

## Supported Source Types

Beanaries supports three ways to get project source code:

1. **GitHub Repositories** - Provide `owner` and `name` (e.g., "rust-lang", "rust")
2. **Arbitrary Git Repositories** - Provide `git_url` (e.g., "https://git.savannah.gnu.org/git/gcc.git")
3. **Direct Downloads** - Provide `source_url` and `extract_command` for tarballs/zip files

## Monorepo Support

Beanaries supports tracking individual subprojects within monorepos like `llvm/llvm-project`. Use the `subproject_path` field to specify which part of the repo to track:

- For LLVM: `"subproject_path": "llvm/"`
- For Clang: `"subproject_path": "clang/"`
- For LLD: `"subproject_path": "lld/"`
- For regular repos: omit this field or leave it empty

This allows you to track multiple subprojects from the same repository as separate entries.

## Configuration Options

### 1. GitHub Actions Scraping

For projects that use GitHub Actions, you can scrape build times directly from their workflow runs.

```bash
curl -X POST http://localhost:8001/projects/with-config \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "llvm",
    "name": "llvm-project",
    "category": "compiler",
    "language": "C++",
    "description": "The LLVM Compiler Infrastructure",
    "github_actions_workflow": "llvm-project-tests.yml",
    "github_actions_job": "build-llvm",
    "platforms": ["ubuntu-latest", "macos-latest"],
    "branch": "main",
    "check_interval_hours": 12
  }'
```

**Required fields for GitHub Actions:**
- `github_actions_workflow`: The workflow file name (e.g., `ci.yml`, `build.yml`)
- Optional: `github_actions_job`: Specific job to track (if not specified, all jobs)

### 2. Local Builds

For projects you want to build locally to measure compile time:

```bash
curl -X POST http://localhost:8001/projects/with-config \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "torvalds",
    "name": "linux",
    "category": "kernel",
    "language": "C",
    "description": "Linux kernel source tree",
    "build_command": "make defconfig && make -j$(nproc)",
    "platforms": ["ubuntu-latest"],
    "branch": "master",
    "check_interval_hours": 24
  }'
```

**Required fields for local builds:**
- `build_command`: The command to build the project
- Optional: `build_dir`: Directory to run build in (relative to repo root)

### 3. Complex Build (with build directory)

Some projects need to be built from a specific directory:

```bash
curl -X POST http://localhost:8001/projects/with-config \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "chromium",
    "name": "chromium",
    "category": "browser",
    "language": "C++",
    "description": "Chromium web browser",
    "build_command": "gn gen out/Default && ninja -C out/Default chrome",
    "build_dir": "src",
    "platforms": ["ubuntu-latest"],
    "branch": "main",
    "check_interval_hours": 24
  }'
```

### 4. Both GitHub Actions AND Local Builds

You can configure both methods for the same project:

```bash
curl -X POST http://localhost:8001/projects/with-config \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "rust-lang",
    "name": "rust",
    "category": "compiler",
    "language": "Rust",
    "description": "Empowering everyone to build reliable and efficient software",
    "github_actions_workflow": "ci.yml",
    "github_actions_job": "test",
    "build_command": "python3 x.py build",
    "platforms": ["ubuntu-latest", "macos-latest", "windows-latest"],
    "branch": "master",
    "check_interval_hours": 12
  }'
```

This will create configurations for:
- GitHub Actions scraping on all 3 platforms
- Local builds on all 3 platforms

## Common Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `owner` | string | Yes | - | Repository owner (GitHub username or domain for others) |
| `name` | string | Yes | - | Repository name |
| `git_url` | string | No | - | Full git URL for non-GitHub repos (e.g., "https://git.savannah.gnu.org/git/gcc.git") |
| `subproject_path` | string | No | - | Path to subproject in monorepo (e.g., "llvm/", "clang/") |
| `source_url` | string | No | - | Direct download URL for source archive (alternative to git) |
| `extract_command` | string | No | - | Command to extract archive (e.g., "tar -xzf", "tar -xJf", "unzip") |
| `category` | enum | No | `other` | Project category (see below) |
| `language` | string | No | - | Primary programming language |
| `description` | string | No | - | Project description |
| `platforms` | array | No | `["ubuntu-latest"]` | Platforms to track |
| `branch` | string | No | `main` | Branch to track (for git sources) |
| `check_interval_hours` | integer | No | 24 | How often to check (1-168) |

## Project Categories

- `compiler` - Compilers (LLVM, GCC, Rust, etc.)
- `kernel` - Operating system kernels (Linux, FreeBSD, etc.)
- `browser` - Web browsers (Chromium, Firefox, etc.)
- `ml_framework` - Machine learning frameworks (PyTorch, TensorFlow, etc.)
- `language_runtime` - Language runtimes (Python, Node.js, etc.)
- `database` - Databases (PostgreSQL, MySQL, etc.)
- `web_framework` - Web frameworks (Django, Rails, etc.)
- `build_tool` - Build tools (CMake, Bazel, etc.)
- `graphics` - Graphics libraries (Mesa, Vulkan, etc.)
- `system_tool` - System tools (systemd, coreutils, etc.)
- `other` - Other projects

## Platforms

- `ubuntu-latest` - Ubuntu (latest LTS)
- `ubuntu-22.04` - Ubuntu 22.04
- `ubuntu-24.04` - Ubuntu 24.04
- `macos-latest` - macOS (latest)
- `macos-13` - macOS 13
- `macos-14` - macOS 14
- `windows-latest` - Windows Server (latest)
- `windows-2022` - Windows Server 2022

## Example Projects

### LLVM (from llvm/llvm-project monorepo)
```bash
# Track LLVM subproject
curl -X POST http://localhost:8001/projects/with-config \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "llvm",
    "name": "llvm-project",
    "subproject_path": "llvm/",
    "category": "compiler",
    "language": "C++",
    "description": "The LLVM Compiler Infrastructure",
    "build_command": "cmake -S llvm -B build -G Ninja && ninja -C build",
    "platforms": ["ubuntu-latest"]
  }'

# Track Clang subproject (separate entry)
curl -X POST http://localhost:8001/projects/with-config \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "llvm",
    "name": "llvm-project",
    "subproject_path": "clang/",
    "category": "compiler",
    "language": "C++",
    "description": "C Language Family Frontend for LLVM",
    "build_command": "cmake -S llvm -B build -G Ninja -DLLVM_ENABLE_PROJECTS=clang && ninja -C build",
    "platforms": ["ubuntu-latest"]
  }'
```

### Linux Kernel (Git)
```bash
curl -X POST http://localhost:8001/projects/with-config \
  -H "Content-Type": application/json" \
  -d '{
    "owner": "torvalds",
    "name": "linux",
    "category": "kernel",
    "language": "C",
    "build_command": "make defconfig && make -j$(nproc)",
    "platforms": ["ubuntu-latest"]
  }'
```

### Linux Kernel (Direct Download)
```bash
curl -X POST http://localhost:8001/projects/with-config \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "kernel.org",
    "name": "linux-6.6.1",
    "category": "kernel",
    "language": "C",
    "description": "Linux kernel 6.6.1",
    "source_url": "https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.6.1.tar.xz",
    "extract_command": "tar -xJf",
    "build_command": "make defconfig && make -j$(nproc)",
    "platforms": ["ubuntu-latest"]
  }'
```

### GCC (Non-GitHub Git)
```bash
curl -X POST http://localhost:8001/projects/with-config \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "git.savannah.gnu.org/git",
    "name": "gcc",
    "git_url": "https://git.savannah.gnu.org/git/gcc.git",
    "category": "compiler",
    "language": "C++",
    "description": "GNU Compiler Collection",
    "build_command": "../configure && make -j$(nproc)",
    "build_dir": "objdir",
    "platforms": ["ubuntu-latest"],
    "branch": "master"
  }'
```

### PyTorch
```bash
curl -X POST http://localhost:8001/projects/with-config \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "pytorch",
    "name": "pytorch",
    "category": "ml_framework",
    "language": "Python",
    "github_actions_workflow": "pull.yml",
    "build_command": "python setup.py build",
    "platforms": ["ubuntu-latest", "macos-latest"]
  }'
```

### TensorFlow
```bash
curl -X POST http://localhost:8001/projects/with-config \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "tensorflow",
    "name": "tensorflow",
    "category": "ml_framework",
    "language": "Python",
    "github_actions_workflow": "build.yml",
    "platforms": ["ubuntu-latest"]
  }'
```

## After Adding Projects

Once you've added projects, you can:

1. **Run the GitHub Actions scraper**:
   ```bash
   cd apps/backend
   uv run python -m src.cli scrape
   ```

2. **Run local builds**:
   ```bash
   cd apps/backend
   uv run python -m src.cli build
   ```

3. **View projects**:
   ```bash
   curl http://localhost:8001/projects
   ```

4. **View configurations**:
   ```bash
   curl http://localhost:8001/configs?project_id=1
   ```

5. **Check the frontend**:
   Open http://localhost:5173 to see the leaderboard and project pages.

## Notes

- At least one of `github_actions_workflow` or `build_command` must be provided
- If you provide both, configurations will be created for both methods
- Each platform in the `platforms` array gets its own configuration
- The scraper respects `check_interval_hours` - it won't re-scrape until enough time has passed
- Build times are only tracked for successful builds (unless the build fails, then failure is recorded)
