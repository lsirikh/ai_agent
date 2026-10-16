"""
Settings Repository

Phase 14.2.2: Settings Repository Implementation
- CRUD operations for settings table
- JSONB value storage
"""

from typing import Any, Dict, Optional
import json

from .base import BaseRepository


class SettingsRepository(BaseRepository):
    """
    Repository for settings table operations.

    Handles CRUD operations for application settings stored as JSONB.

    Usage:
        repo = SettingsRepository()

        # Get a setting
        general = await repo.get("general")

        # Create or update a setting
        await repo.upsert("general", {"language": "ko", "voice_speed": 1.0})

        # Get all settings
        all_settings = await repo.get_all()

        # Delete a setting
        await repo.delete("old_setting")
    """

    async def get(self, key: str) -> Dict[str, Any]:
        """
        Get a setting value by key.

        Args:
            key: The setting key (e.g., "general", "llm", "audio")

        Returns:
            The setting value as a dict, or empty dict if not found
        """
        async with self.connection() as conn:
            row = await conn.fetchrow(
                "SELECT key, value, category FROM settings WHERE key = $1",
                key
            )

            if row is None:
                return {}

            return dict(row["value"]) if row["value"] else {}

    async def upsert(
        self,
        key: str,
        value: Dict[str, Any],
        category: str = "system",
        description: Optional[str] = None
    ) -> None:
        """
        Create or update a setting.

        Uses INSERT ... ON CONFLICT DO UPDATE for atomic upsert.

        Args:
            key: The setting key
            value: The setting value as a dict (stored as JSONB)
            category: Setting category (default: "system")
            description: Optional description of the setting
        """
        async with self.connection() as conn:
            await conn.execute(
                """
                INSERT INTO settings (key, value, category, description, updated_at)
                VALUES ($1, $2::jsonb, $3, $4, NOW())
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    category = EXCLUDED.category,
                    description = COALESCE(EXCLUDED.description, settings.description),
                    updated_at = NOW()
                """,
                key,
                json.dumps(value),
                category,
                description
            )

    async def get_all(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all settings as a dictionary.

        Returns:
            Dict mapping setting keys to their values
        """
        async with self.connection() as conn:
            rows = await conn.fetch(
                "SELECT key, value, category FROM settings ORDER BY key"
            )

            return {
                row["key"]: dict(row["value"]) if row["value"] else {}
                for row in rows
            }

    async def get_by_category(self, category: str) -> Dict[str, Dict[str, Any]]:
        """
        Get all settings in a specific category.

        Args:
            category: The category to filter by

        Returns:
            Dict mapping setting keys to their values
        """
        async with self.connection() as conn:
            rows = await conn.fetch(
                "SELECT key, value FROM settings WHERE category = $1 ORDER BY key",
                category
            )

            return {
                row["key"]: dict(row["value"]) if row["value"] else {}
                for row in rows
            }

    async def delete(self, key: str) -> bool:
        """
        Delete a setting by key.

        Args:
            key: The setting key to delete

        Returns:
            True if a setting was deleted, False if not found
        """
        async with self.connection() as conn:
            result = await conn.execute(
                "DELETE FROM settings WHERE key = $1",
                key
            )

            # asyncpg returns "DELETE N" where N is the number of rows deleted
            return result == "DELETE 1"
