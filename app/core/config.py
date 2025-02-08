from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    ENV: str = "dev"
    OPENAI_BASE_URL: str | None = None
    OPENAI_API_KEY: str
    ELEVENLABS_API_KEY: str
    DEEPGRAM_API_KEY: str

    class Config:
        env_file = ".env"
        


@lru_cache
def get_settings():
    return Settings()
