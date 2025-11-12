import uuid
from sqlalchemy import Column, String, BigInteger, Integer, Float, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from models.base import Base

class Asset(Base):
    __tablename__ = "assets"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(64), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    original_name = Column(String(255), nullable=False)
    storage_key = Column(String(255), nullable=False)
    mime_type = Column(String(128), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

Index("idx_assets_user_id_created_at", Asset.user_id, Asset.created_at.desc())
Index("idx_assets_user_project", Asset.user_id, Asset.project_id, Asset.created_at.desc())
Index("idx_assets_user_storage_key", Asset.user_id, Asset.storage_key, unique=True)
