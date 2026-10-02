"""
StockMind AI — System Prompt Model
Singleton row holding the editable AI system prompt that steers AI-generated
stock commentary and analysis narratives.
"""

import uuid

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.sql import func

from app.database import Base
from app.models.compat import CompatUUID as UUID


class SystemPrompt(Base):
    """Current AI system prompt — one shared row, editable from the UI."""

    __tablename__ = "system_prompts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content = Column(Text, nullable=False)
    source = Column(String(20), nullable=False, default="manual")  # manual | suggested
    updated_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<SystemPrompt source={self.source} updated_by={self.updated_by}>"
