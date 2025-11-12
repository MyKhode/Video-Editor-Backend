import uuid
from sqlalchemy import Column, String, Boolean
from models.base import Base, TimestampMixin

class User(Base, TimestampMixin):
    __tablename__ = "user"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    email_verified = Column(Boolean, default=False, nullable=False)
    image = Column(String(512), nullable=True)
