"""
Backend Database Package

Phase 14.1: Database Infrastructure
- DatabaseManager: Connection pool management
- Repository base classes
"""

from .connection import DatabaseManager, get_db_manager

__all__ = ["DatabaseManager", "get_db_manager"]
