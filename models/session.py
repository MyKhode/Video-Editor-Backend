import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from models.base import Base, TimestampMixin

class Session(Base, TimestampMixin):
    __tablename__ = "session"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    token = Column(String(512), unique=True, nullable=False, index=True)
    ip_address = Column(String(128), nullable=True)
    user_agent = Column(String(512), nullable=True)
    user_id = Column(String(64), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)

Index("idx_session_userId", Session.user_id)
Index("idx_session_token", Session.token)
