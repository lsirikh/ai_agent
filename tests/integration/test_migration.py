"""
Test Migration Validation

Phase 14.5.2: Migration Validation Tests
- test_schema_matches_prd: Schema matches PRD specification
- test_default_settings_exist: Default settings are created
- test_indexes_exist: Required indexes exist
"""

import pytest
import re


class TestSchemaMatchesPRD:
    """Tests for schema matching PRD specification."""

    def test_schema_matches_prd(self):
        """
        Test that init.sql schema matches PRD specification.

        Requirements (from PRD):
        - settings table with key, value(JSONB), category
        - sessions table with id(UUID), user_id, title
        - messages table with session_id FK, role, content, rag_context
        - documents table with status, file_hash
        - document_chunks table with embedding_json
        """
        # Read the schema file
        schema_path = "config/postgres/init.sql"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = f.read()

        # Verify settings table
        assert "CREATE TABLE IF NOT EXISTS settings" in schema
        assert "key VARCHAR" in schema
        assert "value JSONB" in schema
        assert "category VARCHAR" in schema

        # Verify sessions table
        assert "CREATE TABLE IF NOT EXISTS sessions" in schema
        assert "id UUID PRIMARY KEY" in schema
        assert "user_id VARCHAR" in schema
        assert "title VARCHAR" in schema
        assert "last_active_at TIMESTAMP" in schema

        # Verify messages table
        assert "CREATE TABLE IF NOT EXISTS messages" in schema
        assert "session_id UUID NOT NULL REFERENCES sessions" in schema
        assert "role VARCHAR" in schema
        assert "content TEXT NOT NULL" in schema
        assert "rag_context TEXT" in schema
        assert "rag_sources JSONB" in schema

        # Verify documents table
        assert "CREATE TABLE IF NOT EXISTS documents" in schema
        assert "status VARCHAR" in schema
        assert "file_hash VARCHAR" in schema
        assert "chunk_count INTEGER" in schema

        # Verify document_chunks table
        assert "CREATE TABLE IF NOT EXISTS document_chunks" in schema
        assert "document_id UUID NOT NULL REFERENCES documents" in schema
        assert "chunk_index INTEGER" in schema
        assert "content TEXT NOT NULL" in schema
        assert "embedding_json TEXT" in schema

        # Verify personas table
        assert "CREATE TABLE IF NOT EXISTS personas" in schema
        assert "system_prompt TEXT" in schema

    def test_schema_has_uuid_extension(self):
        """
        Test that UUID extension is enabled.
        """
        schema_path = "config/postgres/init.sql"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = f.read()

        assert 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"' in schema

    def test_schema_has_schema_version(self):
        """
        Test that schema version tracking exists.
        """
        schema_path = "config/postgres/init.sql"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = f.read()

        assert "CREATE TABLE IF NOT EXISTS schema_version" in schema
        assert "2.0.0" in schema  # Current version


class TestDefaultSettingsExist:
    """Tests for default settings initialization."""

    def test_default_settings_exist(self):
        """
        Test that default settings are inserted in init.sql.

        Required default settings:
        - general: wake_word, language, voice_speed, wake_word_threshold
        - llm: model, temperature, max_tokens, system_prompt
        - audio: sample_rate, vad_threshold, silence_duration
        """
        schema_path = "config/postgres/init.sql"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = f.read()

        # Verify general settings
        assert "'general'" in schema
        assert "wake_word" in schema
        assert "language" in schema
        assert "voice_speed" in schema
        assert "wake_word_threshold" in schema

        # Verify LLM settings
        assert "'llm'" in schema
        assert "model" in schema
        assert "temperature" in schema
        assert "max_tokens" in schema
        assert "system_prompt" in schema

        # Verify audio settings
        assert "'audio'" in schema
        assert "sample_rate" in schema
        assert "vad_threshold" in schema
        assert "silence_duration" in schema

    def test_default_persona_exists(self):
        """
        Test that default persona is created.
        """
        schema_path = "config/postgres/init.sql"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = f.read()

        assert "EdgeVoice Assistant" in schema
        assert "is_active" in schema

    def test_default_values_are_valid_json(self):
        """
        Test that default setting values are valid JSON.
        """
        import json

        schema_path = "config/postgres/init.sql"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = f.read()

        # Extract JSON values from INSERT statements using regex
        # Looking for patterns like: ('general', '{...}',
        json_pattern = r"'(general|llm|audio)',\s*'(\{[^']*\})'"

        matches = re.findall(json_pattern, schema, re.DOTALL)
        assert len(matches) >= 3, "Should have at least 3 default settings"

        for key, json_str in matches:
            # Remove newlines and extra spaces for parsing
            json_str = json_str.replace('\n', ' ').strip()
            try:
                parsed = json.loads(json_str)
                assert isinstance(parsed, dict)
            except json.JSONDecodeError as e:
                pytest.fail(f"Invalid JSON for {key}: {e}")


class TestIndexesExist:
    """Tests for required indexes."""

    def test_indexes_exist(self):
        """
        Test that required indexes are defined in init.sql.

        Required indexes:
        - idx_settings_category
        - idx_sessions_user_id
        - idx_sessions_last_active
        - idx_messages_session_id
        - idx_messages_created_at
        - idx_documents_status
        - idx_documents_category
        - idx_documents_file_hash
        - idx_chunks_document_id
        """
        schema_path = "config/postgres/init.sql"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = f.read()

        required_indexes = [
            "idx_settings_category",
            "idx_sessions_user_id",
            "idx_sessions_last_active",
            "idx_messages_session_id",
            "idx_messages_created_at",
            "idx_documents_status",
            "idx_documents_category",
            "idx_documents_file_hash",
            "idx_chunks_document_id",
        ]

        for index_name in required_indexes:
            assert index_name in schema, f"Index {index_name} not found in schema"

    def test_foreign_key_constraints_exist(self):
        """
        Test that foreign key constraints are defined.
        """
        schema_path = "config/postgres/init.sql"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = f.read()

        # messages -> sessions FK
        assert "REFERENCES sessions(id)" in schema

        # document_chunks -> documents FK
        assert "REFERENCES documents(id)" in schema

        # Cascade deletes
        assert "ON DELETE CASCADE" in schema

    def test_triggers_exist(self):
        """
        Test that required triggers are defined.
        """
        schema_path = "config/postgres/init.sql"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = f.read()

        # Auto-update updated_at trigger
        assert "update_updated_at_column" in schema
        assert "update_settings_updated_at" in schema
        assert "update_personas_updated_at" in schema

        # Auto-update last_active_at on messages
        assert "update_session_last_active" in schema
        assert "update_session_on_message" in schema


class TestTableConstraints:
    """Tests for table constraints."""

    def test_role_constraint_exists(self):
        """
        Test that role constraint is defined for messages.
        """
        schema_path = "config/postgres/init.sql"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = f.read()

        assert "role IN ('user', 'assistant', 'system')" in schema

    def test_document_status_constraint_exists(self):
        """
        Test that status constraint is defined for documents.
        """
        schema_path = "config/postgres/init.sql"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = f.read()

        assert "status IN ('pending', 'processing', 'indexed', 'failed', 'deleted')" in schema

    def test_audit_action_constraint_exists(self):
        """
        Test that action constraint is defined for audit_log.
        """
        schema_path = "config/postgres/init.sql"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = f.read()

        assert "action IN ('INSERT', 'UPDATE', 'DELETE')" in schema
