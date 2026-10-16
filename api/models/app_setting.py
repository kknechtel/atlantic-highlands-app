"""AppSetting — values an admin sets in the app instead of the server's env.

API keys live here encrypted (see services/app_settings.py), so a new
deployment can be configured from the admin screen without shell access.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text

from database import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String(80), primary_key=True)
    value_encrypted = Column(Text, nullable=False)
    updated_by = Column(String, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
