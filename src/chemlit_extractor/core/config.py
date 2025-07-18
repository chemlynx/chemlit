"""Configuration management for ChemLit Extractor."""

from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # Database Configuration
    database_host: str = Field(default="localhost", description="Database host")
    database_port: int = Field(default=5432, description="Database port")
    database_name: str = Field(default="chemlit_extractor", description="Database name")
    database_user: str = Field(default="postgres", description="Database username")
    database_password: str = Field(default="", description="Database password")

    # FastAPI Configuration
    debug: bool = Field(default=False, description="Enable debug mode")

    # CrossRef API Configuration
    crossref_rate_limit: int = Field(
        default=10, description="CrossRef API rate limit (requests per minute)"
    )
    crossref_user_agent: str = Field(
        default="ChemLitExtractor/0.1.0 (mailto:user@example.com)",
        description="User agent for CrossRef API requests",
    )

    # File Storage Configuration
    data_root_path: Path = Field(
        default=Path("./data"), description="Root path for data storage"
    )
    articles_path: Path = Field(
        default=Path("./data/articles"), description="Path for article storage"
    )
    max_file_size_mb: int = Field(default=100, description="Maximum file size in MB")

    @computed_field
    @property
    def database_url(self) -> str:
        """Construct database URL from components."""
        return (
            f"postgresql://{self.database_user}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )

    def model_post_init(self, __context: dict | None = None) -> None:
        """Create necessary directories after model initialization."""
        self.data_root_path.mkdir(parents=True, exist_ok=True)
        self.articles_path.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
