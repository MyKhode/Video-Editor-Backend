from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.config import settings
# Use the same Base as models to ensure one metadata registry
from models.base import Base

engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    pool_pre_ping=True,
    pool_recycle=3600,
    future=True
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
