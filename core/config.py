from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: str
    DB_NAME: str

    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    BACKEND_URL: str
    FRONTEND_URL: str
    MEDIA_DIR: str = "media"
    MEDIA_URL_PATH: str = "/media"

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    class Config:
        env_file = ".env"

settings = Settings()
