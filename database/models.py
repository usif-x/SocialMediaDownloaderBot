from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from database.database import Base


class User(Base):
    """User model"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    language_code = Column(String(10), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    downloads = relationship("Download", back_populates="user")

    def __repr__(self):
        return f"<User(telegram_id={self.telegram_id}, username={self.username})>"


class Download(Base):
    """Download history model"""

    __tablename__ = "downloads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    url = Column(Text, nullable=False)
    title = Column(String(500), nullable=True)
    platform = Column(String(100), nullable=True)
    duration = Column(Integer, nullable=True)  # in seconds
    views = Column(BigInteger, nullable=True)
    quality = Column(String(50), nullable=True)
    format_type = Column(String(20), nullable=True)  # video, audio, image
    file_size = Column(BigInteger, nullable=True)  # in bytes
    message_id = Column(BigInteger, nullable=True)  # Telegram message ID for restore
    file_id = Column(String(255), nullable=True)  # Telegram file_id for restore
    status = Column(
        String(50), default="pending"
    )  # pending, processing, completed, failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Relationship
    user = relationship("User", back_populates="downloads")

    def __repr__(self):
        return f"<Download(id={self.id}, title={self.title}, status={self.status})>"


class MandatoryChannel(Base):
    """Mandatory subscription channels"""

    __tablename__ = "mandatory_channels"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(BigInteger, unique=True, nullable=False)
    channel_name = Column(String(255), nullable=True)
    channel_link = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<MandatoryChannel(id={self.id}, name={self.channel_name})>"


class BotSetting(Base):
    """Bot configuration settings"""

    __tablename__ = "bot_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(50), unique=True, nullable=False)
    value = Column(String(255), nullable=True)
    
    def __repr__(self):
        return f"<BotSetting(key={self.key}, value={self.value})>"
