"""
Backend Repositories Package

Phase 14.2: Repository Layer
- BaseRepository: Abstract base class for all repositories
- SettingsRepository: CRUD for settings table
- SessionRepository: CRUD for sessions table
- MessageRepository: CRUD for messages table
- DocumentRepository: CRUD for documents table
- PipelineLogRepository: CRUD for pipeline_logs table (Phase 17)
- Connection and transaction context managers
"""

from .base import BaseRepository
from .settings_repository import SettingsRepository
from .session_repository import SessionRepository
from .message_repository import MessageRepository
from .document_repository import DocumentRepository
from .pipeline_log_repository import PipelineLogRepository

__all__ = [
    "BaseRepository",
    "SettingsRepository",
    "SessionRepository",
    "MessageRepository",
    "DocumentRepository",
    "PipelineLogRepository",
]
