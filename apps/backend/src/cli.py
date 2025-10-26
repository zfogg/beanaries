"""CLI commands for managing the Beanaries backend."""
import asyncio
import csv
import sys
from pathlib import Path

from sqlalchemy import select

from .database import AsyncSessionLocal, init_db
from .models import DataSource, Platform, Project, ProjectCategory, ProjectConfig
from .scrapers.github_actions import GitHubActionsScraper
from .scrapers.local_builder import LocalBuilder


async def scrape_github_actions():
    """Scrape GitHub Actions for all enabled configurations."""
    print("Starting GitHub Actions scraper...")

    scraper = GitHubActionsScraper()
    async with AsyncSessionLocal() as db:
        stats = await scraper.scrape_all_configs(db)

    print(f"\nScraping complete:")
    print(f"  Configs checked: {stats['total_configs']}")
    print(f"  Builds created: {stats['total_builds']}")
    print(f"  Errors: {stats['errors']}")


async def run_local_builds():
    """Run local builds for all enabled configurations."""
    print("Starting local builds...")

    builder = LocalBuilder()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ProjectConfig, Project)
            .join(Project)
            .where(
                ProjectConfig.is_enabled == True,
                ProjectConfig.data_source == "local_build",
                Project.is_active == True,
            )
        )

        configs_projects = result.all()
        print(f"Found {len(configs_projects)} enabled local build configs")

        for config, project in configs_projects:
            try:
                print(f"\nBuilding {project.full_name}...")
                created = await builder.build_config(config, project, db)
                if created:
                    print(f"  + Build recorded")
                else:
                    print(f"  - Already have this commit")
            except Exception as e:
                print(f"  - Error: {e}")
                continue

        await db.commit()


async def build_project():
    """Build a specific project by ID or name."""
    if len(sys.argv) < 3:
        print("Usage: python -m src.cli build-project <project_id_or_name>")
        print("\nExample:")
        print("  python -m src.cli build-project 1")
        print("  python -m src.cli build-project \"golang/go\"")
        sys.exit(1)

    identifier = sys.argv[2]

    builder = LocalBuilder()
    async with AsyncSessionLocal() as db:
        # Try to parse as integer (ID)
        try:
            project_id = int(identifier)
            project = await db.get(Project, project_id)
        except ValueError:
            # Treat as full_name
            result = await db.execute(
                select(Project).where(Project.full_name == identifier)
            )
            project = result.scalar_one_or_none()

        if not project:
            print(f"Error: Project '{identifier}' not found")
            sys.exit(1)

        # Get all enabled local_build configs for this project
        result = await db.execute(
            select(ProjectConfig)
            .where(
                ProjectConfig.project_id == project.id,
                ProjectConfig.data_source == DataSource.LOCAL_BUILD,
                ProjectConfig.is_enabled == True,
            )
        )
        configs = result.scalars().all()

        if not configs:
            print(f"Error: No enabled local_build configurations found for {project.full_name}")
            print(f"\nTo add a configuration, create a ProjectConfig with:")
            print(f"  - data_source: LOCAL_BUILD")
            print(f"  - build_command: <your build command>")
            print(f"  - platform: <platform>")
            sys.exit(1)

        print(f"Building {project.full_name} ({len(configs)} config(s))...\n")

        for config in configs:
            try:
                print(f"Config #{config.id} (platform: {config.platform}):")
                print(f"  Build command: {config.build_command}")
                if config.build_dir:
                    print(f"  Build directory: {config.build_dir}")
                print()

                created = await builder.build_config(config, project, db)
                if created:
                    print(f"  + Build recorded\n")
                else:
                    print(f"  - Already have this commit\n")
            except Exception as e:
                print(f"  - Error: {e}\n")
                import traceback
                traceback.print_exc()
                continue

        await db.commit()
        print("Done!")


async def list_projects():
    """List all tracked projects."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Project).order_by(Project.stars.desc())
        )
        projects = result.scalars().all()

        print(f"\nTracked Projects ({len(projects)}):")
        print("-" * 80)
        for project in projects:
            status = "+" if project.is_active else "-"
            print(f"{status} {project.full_name:40} {project.category:20} * {project.stars}")


async def init_database():
    """Initialize the database schema."""
    print("Initializing database...")
    await init_db()
    print("Database initialized")


async def import_projects():
    """Import projects from projects.csv file."""
    # Look for projects.csv in current directory or parent directory (repo root)
    csv_path = Path("projects.csv")
    if not csv_path.exists():
        csv_path = Path("../../projects.csv")
    if not csv_path.exists():
        print(f"Error: projects.csv not found in current or parent directory")
        sys.exit(1)

    print(f"Reading projects from {csv_path}...")

    async with AsyncSessionLocal() as db:
        projects_created = 0
        configs_created = 0
        skipped = 0

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                owner = row["owner"]
                name = row["name"]
                category = row["category"]
                language = row["language"]
                description = row["description"]
                workflow_file = row["workflow_file"]
                platforms_str = row["platforms"]

                # Check if project already exists
                result = await db.execute(
                    select(Project).where(
                        Project.owner == owner,
                        Project.name == name,
                    )
                )
                existing_project = result.scalar_one_or_none()

                if existing_project:
                    print(f"  - {owner}/{name} (already exists)")
                    skipped += 1
                    continue

                # Create project
                project = Project(
                    owner=owner,
                    name=name,
                    full_name=f"{owner}/{name}",
                    url=f"https://github.com/{owner}/{name}",
                    description=description,
                    language=language,
                    category=ProjectCategory(category),
                    stars=0,
                    is_active=True,
                )
                db.add(project)
                await db.flush()  # Get the project ID
                projects_created += 1

                # Parse platforms
                platforms = [p.strip() for p in platforms_str.split(",")]

                # Create config for each platform
                for platform_str in platforms:
                    try:
                        platform = Platform(platform_str)
                    except ValueError:
                        print(f"  ! Invalid platform '{platform_str}' for {owner}/{name}, skipping")
                        continue

                    config = ProjectConfig(
                        project_id=project.id,
                        data_source=DataSource.GITHUB_ACTIONS,
                        workflow_file=workflow_file,
                        job_name=None,  # Scrape all jobs
                        platform=platform,
                        branch="main",
                        is_enabled=True,
                        check_interval_hours=24,
                    )
                    db.add(config)
                    configs_created += 1

                print(f"  + {owner}/{name} ({len(platforms)} platform(s))")

        await db.commit()

    print(f"\nImport complete:")
    print(f"  Projects created: {projects_created}")
    print(f"  Configs created: {configs_created}")
    print(f"  Skipped (existing): {skipped}")
    print(f"\nRun 'python -m src.cli scrape-parallel' to scrape all projects in parallel")


async def scrape_parallel():
    """Scrape all projects in parallel with concurrency limit."""
    print("Starting parallel scraper...")

    scraper = GitHubActionsScraper()
    async with AsyncSessionLocal() as db:
        # Get all enabled configs
        result = await db.execute(
            select(ProjectConfig, Project)
            .join(Project)
            .where(
                ProjectConfig.is_enabled == True,
                ProjectConfig.data_source == DataSource.GITHUB_ACTIONS,
                Project.is_active == True,
            )
        )
        configs_projects = result.all()

        print(f"Found {len(configs_projects)} enabled config(s)")

    # Scrape with concurrency limit of 5
    semaphore = asyncio.Semaphore(5)

    async def scrape_with_limit(config_id, project_id, project_full_name, workflow_file):
        async with semaphore:
            # Each scrape gets its own session to avoid transaction contamination
            async with AsyncSessionLocal() as db:
                try:
                    # Fetch fresh config and project
                    config = await db.get(ProjectConfig, config_id)
                    project = await db.get(Project, project_id)

                    if not config or not project:
                        print(f"  - {project_full_name}: Config or project not found")
                        return 0

                    print(f"  Scraping {project_full_name} ({workflow_file})...")
                    builds_count = await scraper.scrape_config(config, project, db)
                    print(f"  + {project_full_name}: {builds_count} builds")
                    return builds_count
                except Exception as e:
                    print(f"  - {project_full_name}: {e}")
                    # Rollback the failed session
                    await db.rollback()
                    return 0

    tasks = [
        scrape_with_limit(config.id, project.id, project.full_name, config.workflow_file)
        for config, project in configs_projects
    ]

    results = await asyncio.gather(*tasks)
    total_builds = sum(results)

    print(f"\nParallel scraping complete:")
    print(f"  Total builds created: {total_builds}")


COMMANDS = {
    "scrape": scrape_github_actions,
    "scrape-parallel": scrape_parallel,
    "build": run_local_builds,
    "build-project": build_project,
    "list": list_projects,
    "init-db": init_database,
    "import": import_projects,
}


def main():
    """Main CLI entrypoint."""
    if len(sys.argv) < 2:
        print("Usage: python -m src.cli <command>")
        print("\nAvailable commands:")
        for cmd in COMMANDS:
            print(f"  {cmd}")
        sys.exit(1)

    command = sys.argv[1]
    if command not in COMMANDS:
        print(f"Unknown command: {command}")
        print(f"Available commands: {', '.join(COMMANDS.keys())}")
        sys.exit(1)

    asyncio.run(COMMANDS[command]())


if __name__ == "__main__":
    main()
