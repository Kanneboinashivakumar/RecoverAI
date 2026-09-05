from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:changeme@db:5432/recoverai"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
