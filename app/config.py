from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite+aiosqlite:///data/transcriber.db"
    sqlite_path: str = "data/transcriber.db"

    # Whisper
    whisper_model: str = "medium"
    transcription_timeout_seconds: int = 3600  # 1 hour
    download_timeout_seconds: int = 600  # 10 minutes

    # AI Provider
    ai_provider: str = "claude"
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"

    # Server
    host: str = "0.0.0.0"
    port: int = 8765

    # Paths
    temp_audio_dir: str = "data/temp_audio"
    data_dir: str = "data"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

# Ensure directories exist
Path(settings.temp_audio_dir).mkdir(parents=True, exist_ok=True)
Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
