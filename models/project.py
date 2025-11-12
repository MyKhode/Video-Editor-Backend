import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Index, JSON
from models.base import Base, TimestampMixin

class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(64), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    timeline = Column(JSON, nullable=True)
    text_bin_items = Column(JSON, nullable=True)

Index("idx_projects_user_id_created_at", Project.user_id, Project.created_at.desc())
