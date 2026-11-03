"""Configuration module for MS2 RevisaTEC Analysis."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    COSMOS_CONNECTION_STRING: str = ""
    COSMOS_DB_NAME: str = "revisatec"
    QUEUE_CONNECTION_STRING: str = ""
    QUEUE_NAME: str = "notificaciones"
    PORT: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
