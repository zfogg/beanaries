# LUCI Commit Validation System

This document describes the commit validation system for LUCI projects to ensure we only track builds from the correct repositories.

## Overview

The LUCI scraper now validates that commit SHAs exist in the tracked repository before adding builds to the database. This prevents builds from unrelated repositories or branches from being included.

## Architecture

### 1. Repository Configuration

Each LUCI project's `scraper_config` includes a `repo_path` field:

```json
{
  "project": "flutter",
  "bucket": "prod",
  "builder": "Linux analyze",
  "repo_path": "repos/flutter"
}
```

The `repo_path` can be:
- **Relative path**: Resolved relative to `apps/backend/` (e.g., `"repos/flutter"`)
- **Absolute path**: Used as-is (e.g., `"/path/to/repos/flutter"`)

### 2. Validation Process

When scraping builds, the `LUCIScraper` (`src/scrapers/luci.py`):

1. **Extracts commit SHAs** from all builds fetched from the LUCI API
2. **Validates commits** using `git cat-file --batch-check` in the configured repository
3. **Filters builds** to only include those with valid commits
4. **Reports filtering** when invalid commits are found

Example output:
```
Fetching builds from LUCI (limit: 100)...
Fetched 100 builds from API
Validating 95 commits against repository...
⚠️  Filtered out 3 builds with commits not in tracked repository
Added 92 builds to database
```

### 3. Implementation Details

#### Commit Validation Method

```python
def validate_commits_in_repo(self, repo_path: Path, commit_shas: list[str]) -> set[str]:
    """
    Uses git cat-file --batch-check to efficiently validate multiple commits.
    Returns a set of valid commit SHAs that exist in the repository.
    """
```

**Performance**: Batch validation is much faster than checking commits individually. For 1000 commits, batch validation takes ~1 second vs ~16 seconds for individual checks.

#### Scraper Integration

The validation is integrated into `scrape_config()`:

```python
# Get repository path from config
repo_path = scraper_config.get("repo_path")

# Validate commits if repo_path is configured
if repo_path and repo_path.exists():
    valid_commits = self.validate_commits_in_repo(repo_path, commit_shas)
    # Filter builds to only include those with valid commits
```

## Flutter Example

### Problem

Flutter's LUCI "Linux analyze" builder tracks the **Flutter framework** repository, not the **Flutter engine** repository. Initially, we were cloning the engine repository, which caused:

- 0 builds updated with commit messages (commits didn't exist)
- Potential for builds from wrong repository to be tracked

### Solution

1. **Updated repository**:
   - Changed from: `https://github.com/flutter/engine.git`
   - Changed to: `https://flutter.googlesource.com/mirrors/flutter` (framework)
   - Updated in `setup_and_backfill_all_repos.py`

2. **Added repo_path to config**:
   ```json
   {
     "project": "flutter",
     "bucket": "prod",
     "builder": "Linux analyze",
     "repo_path": "repos/flutter"
   }
   ```

3. **Cleaned up invalid builds**:
   - Ran `clean_flutter_invalid_builds.py`
   - Deleted 12 builds (0.2%) with commits not in tracked repository

4. **Enabled validation**:
   - Scraper now validates all commits before adding builds
   - Future builds with invalid commits are automatically filtered out

### Results

- **Before**: 0/7,747 builds with commit messages (wrong repository)
- **After**: 2,658/7,735 builds with commit messages (34% coverage)
- **Validation**: Enabled to prevent future invalid builds

## Configuration for All LUCI Projects

### Current Projects

| Project | Repository | Builder | Repo Path |
|---------|-----------|---------|-----------|
| Chromium | chromium/src | Linux Builder | repos/chromium |
| Fuchsia | fuchsia/fuchsia | gcc_toolchain.bringup.x64-gcc | repos/fuchsia |
| Dart | dart-lang/sdk | analyzer-linux-release | repos/dart-sdk |
| Flutter | flutter/mirrors | Linux analyze | repos/flutter |
| WebRTC | webrtc/src | Android32 | repos/webrtc |
| V8 | v8/v8 | Linux Debug Builder | repos/v8 |

### Adding New LUCI Projects

When adding a new LUCI project in `add_luci_projects.py`, include:

1. **Repository directory**: Add `repo_dir` to the project data
2. **Builder configuration**: Ensure builder tracks the correct repository
3. **Repo path**: Automatically included via:
   ```python
   "repo_path": f"repos/{proj_data.get('repo_dir', proj_data['full_name'].split('/')[1])}"
   ```

### Setup Process

1. **Clone repositories** using `setup_and_backfill_all_repos.py`:
   ```bash
   uv run python setup_and_backfill_all_repos.py
   ```

2. **Scrape builds** with validation enabled:
   ```bash
   uv run python scrape_all_luci_projects.py
   ```

3. **Backfill commit messages** from local repositories:
   - Automatically done by `setup_and_backfill_all_repos.py`
   - Or run manually: `uv run python -c "from backfill_commit_messages import backfill_commit_messages; ..."`

## Maintenance

### Cleaning Invalid Builds

Use `clean_flutter_invalid_builds.py` as a template to clean invalid builds for any project:

```python
# 1. Get project and builds
project = db.query(Project).filter_by(full_name="project/name").first()
builds = db.query(Build).filter_by(project_id=project.id).all()

# 2. Validate commits against repository
valid_commits = check_commits_exist(repo_path, commit_shas)

# 3. Delete invalid builds
invalid_builds = [b for b in builds if b.commit_sha not in valid_commits]
db.delete_all(invalid_builds)
```

### Monitoring

Check validation warnings in scraper logs:

```
⚠️  Filtered out N builds with commits not in tracked repository
```

Investigate if:
- Number is high (> 5% of builds)
- Consistently filtering builds
- Repository configuration may be incorrect

## Benefits

1. **Data Integrity**: Only builds from tracked repositories are included
2. **Accurate Commit Messages**: Backfill can successfully populate commit messages
3. **Performance**: Batch validation is very fast (~1 second for 1000 commits)
4. **Fail-Safe**: Validation errors result in builds not being added (vs. adding invalid data)
5. **Transparency**: Clear logging when builds are filtered out

## Related Files

- **Scraper**: `src/scrapers/luci.py` - Main scraper with validation
- **Project Setup**: `add_luci_projects.py` - Configure new LUCI projects
- **Repository Setup**: `setup_and_backfill_all_repos.py` - Clone repos and backfill
- **Cleanup**: `clean_flutter_invalid_builds.py` - Remove invalid builds
- **Config Update**: `update_flutter_config.py` - Add repo_path to existing projects
