"""Add a simple project for testing local builds."""
import asyncio

from sqlalchemy import select

from src.database import AsyncSessionLocal, init_db
from src.models import DataSource, Platform, Project, ProjectCategory, ProjectConfig


async def add_simple_project():
    """Create a simple test project for local builds - fzf (fuzzy finder in Go)."""
    await init_db()

    async with AsyncSessionLocal() as db:
        # Check if project already exists
        result = await db.execute(
            select(Project).where(Project.full_name == "junegunn/fzf")
        )
        existing = result.scalar_one_or_none()

        if existing:
            print("Project junegunn/fzf already exists!")
            print(f"  Project ID: {existing.id}")

            # Check for local build configs
            result = await db.execute(
                select(ProjectConfig).where(
                    ProjectConfig.project_id == existing.id,
                    ProjectConfig.data_source == DataSource.LOCAL_BUILD
                )
            )
            configs = result.scalars().all()
            if configs:
                print(f"  Local build configs: {len(configs)}")
                for config in configs:
                    print(f"    - Config #{config.id}: {config.platform}")
                    print(f"      Build command: {config.build_command}")
            else:
                print("  No local build configs found. Adding one...")
                config = ProjectConfig(
                    project_id=existing.id,
                    data_source=DataSource.LOCAL_BUILD,
                    platform=Platform.WINDOWS_LATEST,
                    branch="master",
                    build_command="go build",
                    build_dir=None,
                    is_enabled=True,
                    check_interval_hours=24,
                )
                db.add(config)
                await db.commit()
                print(f"  Added local build config #{config.id}")

            print(f"\nTo test, run:")
            print(f'  cd apps/backend')
            print(f'  uv run python -m src.cli build-project {existing.id}')
            return

        # Create fzf project - a simple Go project (just needs "go build")
        project = Project(
            owner="junegunn",
            name="fzf",
            full_name="junegunn/fzf",
            url="https://github.com/junegunn/fzf",
            description="Command-line fuzzy finder (Go project, very simple to build)",
            language="Go",
            category=ProjectCategory.DEVTOOLS,
            stars=65000,
            is_active=True,
        )
        db.add(project)
        await db.flush()

        # Create a local build config for Windows
        # fzf just needs "go build" - very simple!
        config = ProjectConfig(
            project_id=project.id,
            data_source=DataSource.LOCAL_BUILD,
            platform=Platform.WINDOWS_LATEST,
            branch="master",
            build_command="go build",
            build_dir=None,
            is_enabled=True,
            check_interval_hours=24,
        )
        db.add(config)

        await db.commit()

        print("Project junegunn/fzf created successfully!")
        print(f"  Project ID: {project.id}")
        print(f"  Name: {project.full_name}")
        print(f"  URL: {project.url}")
        print(f"  Config ID: {config.id}")
        print(f"  Build command: {config.build_command}")
        print(f"\nTo test, run:")
        print(f"  cd apps/backend")
        print(f'  uv run python -m src.cli build-project {project.id}')
        print(f'  # or: uv run python -m src.cli build-project "junegunn/fzf"')
        print(f"\nNote: This requires Go to be installed (https://go.dev/dl/)")


if __name__ == "__main__":
    asyncio.run(add_simple_project())
