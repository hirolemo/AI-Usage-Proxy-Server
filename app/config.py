from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000

    # Ollama settings
    ollama_base_url: str = "http://localhost:11434"

    # Database settings
    database_url: str = "sqlite+aiosqlite:///./db/proxy.db"
    database_path: str = "./db/proxy.db"

    # Admin settings
    admin_api_key: str = "admin-secret-key"

    # Default rate limits for new users
    default_requests_per_minute: int = 60
    default_requests_per_day: int = 1000
    default_tokens_per_minute: int = 100000
    default_tokens_per_day: int = 1000000
    default_total_token_limit: int | None = None  # None means unlimited

    # File upload settings
    max_upload_size_mb: int = 10
    allowed_image_types: list[str] = ["image/jpeg", "image/png", "image/gif", "image/webp"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
