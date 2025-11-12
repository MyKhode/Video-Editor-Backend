import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from models.base import Base, TimestampMixin

class Account(Base, TimestampMixin):
    __tablename__ = "account"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id = Column(String(255), nullable=True)
    provider_id = Column(String(255), nullable=True)
    user_id = Column(String(64), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    access_token = Column(String(1024), nullable=True)
    refresh_token = Column(String(1024), nullable=True)
    id_token = Column(String(1024), nullable=True)
    access_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    refresh_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    scope = Column(String(512), nullable=True)
    password = Column(String(255), nullable=True)

Index("idx_account_userId", Account.user_id)
