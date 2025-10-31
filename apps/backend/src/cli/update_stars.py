"""Update GitHub star counts for projects.

Usage:
    # Update all GitHub projects
    uv run python -m src.cli.update_stars

    # Update specific projects
    uv run python -m src.cli.update_stars rust-lang/rust gcc/gcc

    # Force update even if project is not on GitHub
    uv run python -m src.cli.update_stars --force some/project
"""
import asyncio

import click
import httpx
from sqlalchemy import select, update

from src.config import settings
from src.database import AsyncSessionLocal
from src.models import Project


async def update_project_stars(
    project: Project, client: httpx.AsyncClient, force: bool = False
):
    """Update stars for a single project.

    Args:
        project: Project model instance
        client: HTTP client
        force: If True, attempt update even for non-GitHub projects
    """
    # Skip non-GitHub projects unless forced
    if not force and (not project.url or "github.com" not in project.url):
        click.echo(
            click.style(f"[SKIP] {project.full_name}", fg="yellow")
            + " - not a GitHub project"
        )
        return False

    try:
        # GitHub API endpoint: https://api.github.com/repos/{owner}/{repo}
        api_url = f"https://api.github.com/repos/{project.full_name}"
        click.echo(f"[FETCH] {project.full_name}...", nl=False)

        response = await client.get(api_url)
        response.raise_for_status()

        data = response.json()
        stars = data.get("stargazers_count", 0)

        # Update project stars in database
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Project).where(Project.id == project.id).values(stars=stars)
            )
            await db.commit()

        click.echo(f" {click.style(f'{stars:,} stars', fg='green')}")
        return True

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            click.echo(
                click.style(" NOT FOUND (might be moved or deleted)", fg="red")
            )
        elif e.response.status_code == 403:
            click.echo(
                click.style(
                    " RATE LIMITED - please wait or add GITHUB_TOKEN to .env", fg="red"
                )
            )
            raise  # Raise to stop processing
        else:
            click.echo(click.style(f" ERROR: {e}", fg="red"))
    except Exception as e:
        click.echo(click.style(f" ERROR: {e}", fg="red"))

    return False


@click.command()
@click.argument("projects", nargs=-1)
@click.option(
    "--force",
    is_flag=True,
    help="Attempt to update even if project is not detected as a GitHub project",
)
def main(projects: tuple[str], force: bool):
    """Update GitHub star counts for projects.

    PROJECTS: Project full names to update (e.g., rust-lang/rust).
    If none specified, updates all projects.
    """

    async def run():
        # Get GitHub token from settings (optional - higher rate limit with token)
        headers = {}
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"
            click.echo(click.style("Using GitHub token for authentication", fg="green"))
        else:
            click.echo(
                click.style(
                    "No GITHUB_TOKEN found in .env - using unauthenticated requests (60 req/hour limit)",
                    fg="yellow",
                )
            )
        click.echo()

        async with AsyncSessionLocal() as db:
            if projects:
                # Update specific projects
                project_list = []
                for project_name in projects:
                    result = await db.execute(
                        select(Project).where(Project.full_name == project_name)
                    )
                    project = result.scalar_one_or_none()

                    if not project:
                        click.echo(
                            click.style(
                                f"[ERROR] Project not found: {project_name}", fg="red"
                            )
                        )
                        continue

                    project_list.append(project)
            else:
                # Update all projects
                result = await db.execute(select(Project))
                project_list = result.scalars().all()

            click.echo(f"Found {len(project_list)} project(s) to update\n")

            updated = 0
            async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
                try:
                    for project in project_list:
                        if await update_project_stars(project, client, force):
                            updated += 1

                        # Small delay to avoid rate limiting
                        await asyncio.sleep(0.5)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 403:
                        # Stop on rate limit
                        click.echo(click.style("\nStopped due to rate limiting", fg="red"))

            click.echo()
            click.echo(
                click.style(
                    f"Star update complete! Updated {updated}/{len(project_list)} projects",
                    fg="green",
                )
            )

    asyncio.run(run())


if __name__ == "__main__":
    main()
