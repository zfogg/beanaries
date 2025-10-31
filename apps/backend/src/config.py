from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/beanaries"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8001
    api_reload: bool = True

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173", "http://localhost:5174"]

    # GitHub
    github_token: str | None = None

    # Buildkite
    buildkite_api_token: str | None = None

    # OpenSUSE Build Service
    opensuse_build_token: str | None = None
    opensuse_build_username: str | None = None

    # Firecrawl
    firecrawl_api_key: str | None = None

    # App
    debug: bool = True


settings = Settings()
