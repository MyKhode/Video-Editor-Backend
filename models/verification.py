import uuid
from sqlalchemy import Column, String, DateTime
from models.base import Base, TimestampMixin

class Verification(Base, TimestampMixin):
    __tablename__ = "verification"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    identifier = Column(String(255), nullable=False)
    value = Column(String(1024), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
