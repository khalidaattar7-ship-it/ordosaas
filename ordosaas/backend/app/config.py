"""Application configuration loaded from environment variables."""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Core ---
    DATABASE_URL: str = "postgresql+asyncpg://ordosaas_app:dev_password_change_me@postgres:5432/ordosaas"
    SECRET_KEY: str = "change_this_to_a_random_64_char_string_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    ENVIRONMENT: str = "development"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # --- Scheduling engine tuning ---
    SEUIL_EXACT: int = 50  # Au-delà, LNS au lieu de CP-SAT direct
    CPSAT_TIMEOUT: int = 30
    MAX_JOBS_PAR_FENETRE: int = 50
    MIN_JOBS_PAR_FENETRE: int = 5
    PROFONDEUR_MAX: int = 4
    MAX_ITERATIONS: int = 5
    EPSILON: float = 0.01
    JUNCTION_RADIUS: int = 10

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


settings = Settings()
