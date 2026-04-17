from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str
    ALGORITHM: str
    ENCRYPTION_KEY: str
    ENCRYPTION_ALGORITHM: str = "A256GCM"
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int
    DATABASE_URL: str

    # SMTP settings
    SMTP_HOST: str
    SMTP_PORT: int
    SMTP_USER: str
    SMTP_PASSWORD: str
    SMTP_FROM_EMAIL: str
    OLLAMA_API_URL: str = (
        "http://localhost:11434/api/generate"  # Default for local Ollama
    )
    CLOUDINARY_CLOUD_NAME: str | None = None
    CLOUDINARY_API_KEY: str | None = None
    CLOUDINARY_API_SECRET: str | None = None
    KOSHCONNECT_BASE_URL: str = "https://koshconnect.onrender.com"
    KOSHCONNECT_SIGNING_SECRET: str | None = None
    KOSHCONNECT_SIGN_TOKEN_REQUEST: bool = False

    class Config:
        env_file = ".env"


settings = Settings()
