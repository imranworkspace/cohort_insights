from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "cohort_insights"
    redis_url: str = "redis://localhost:6379/0"
    worker_poll_seconds: float = 1.0
    cache_ttl_seconds: int = 86400
    active_job_ttl_seconds: int = 3600

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
