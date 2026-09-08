from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "silent_orchestra.db"


class Settings(BaseSettings):
    app_name: str = "SilentOrchestra 2.0"
    api_prefix: str = "/api/v1"
    database_url: str = f"sqlite:///{DEFAULT_DATABASE}"
    suggestion_threshold: int = 3
    auto_execution_threshold: float = 0.60
    enable_os_actions: bool = False
    require_active_window: bool = True
    demo_mode: bool = True
    allowed_origins: str = "http://127.0.0.1:8000,http://localhost:8000"

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_prefix="SO_",
        extra="ignore",
    )

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]


settings = Settings()
