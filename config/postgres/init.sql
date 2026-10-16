-- ============================================
-- EdgeVoice PostgreSQL Schema v2.0
-- Phase 14: Database Architecture & Integration
-- ============================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable pgvector extension for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================
-- SETTINGS TABLE
-- ============================================
-- Stores application configuration with JSONB for flexible schema

CREATE TABLE IF NOT EXISTS settings (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB NOT NULL DEFAULT '{}',
    category VARCHAR(50) NOT NULL DEFAULT 'system',
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for category-based queries
CREATE INDEX IF NOT EXISTS idx_settings_category ON settings(category);

-- Default settings (Master settings only)
INSERT INTO settings (key, value, category, description) VALUES
    ('general', '{
        "wake_word": "hey_jarvis",
        "language": "ko",
        "voice_speed": 1.0,
        "wake_word_threshold": 0.5
    }', 'user', 'User-facing general settings'),

    ('llm', '{
        "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
        "temperature": 0.7,
        "max_tokens": 1024,
        "system_prompt": "당신은 EdgeVoice AI 어시스턴트입니다. 사용자의 질문에 친절하고 정확하게 한국어로만 답변해주세요."
    }', 'ai', 'LLM model configuration'),

    ('audio', '{
        "sample_rate": 16000,
        "vad_threshold": 0.5,
        "silence_duration": 0.5
    }', 'audio', 'Audio processing settings')
ON CONFLICT (key) DO NOTHING;

-- ============================================
-- SESSIONS TABLE
-- ============================================
-- Stores chat session information
-- Phase 18.3.2: Added session_type and source columns

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(100),
    title VARCHAR(255),
    session_type VARCHAR(20) NOT NULL DEFAULT 'web' CHECK (session_type IN ('web', 'voice', 'unified')),
    source VARCHAR(50) NOT NULL DEFAULT 'web' CHECK (source IN ('web', 'orchestrator', 'api')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_active_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Index for user queries
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_last_active ON sessions(last_active_at DESC);

-- ============================================
-- MESSAGES TABLE
-- ============================================
-- Stores individual chat messages
-- Phase 18.3.2: Added source and audio_url columns

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    source VARCHAR(50) DEFAULT 'web' CHECK (source IN ('web', 'voice', 'api')),
    audio_url TEXT,
    rag_context TEXT,
    rag_sources JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for session-based queries
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at DESC);

-- ============================================
-- SESSION_SUMMARIES TABLE
-- ============================================
-- Rolling summaries of old turns (original messages are kept)
-- The backend also creates this on startup for existing databases.

CREATE TABLE IF NOT EXISTS session_summaries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    summary TEXT NOT NULL,
    covered_until_message_id UUID NOT NULL,
    token_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_session_summaries_session ON session_summaries(session_id, created_at DESC);

-- ============================================
-- DOCUMENTS TABLE
-- ============================================
-- Stores uploaded document metadata for RAG

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255),
    file_type VARCHAR(50),
    file_size BIGINT,
    file_hash VARCHAR(64),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'indexed', 'failed', 'deleted')),
    chunk_count INTEGER DEFAULT 0,
    title VARCHAR(255),
    category VARCHAR(100),
    tags JSONB DEFAULT '[]',
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    indexed_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}'
);

-- Indexes for document queries
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_category ON documents(category);
CREATE INDEX IF NOT EXISTS idx_documents_file_hash ON documents(file_hash);

-- ============================================
-- DOCUMENT_CHUNKS TABLE
-- ============================================
-- Stores document chunks with embeddings for RAG

CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_hash VARCHAR(64),
    embedding_json TEXT,
    embedding vector(1024),
    start_char INTEGER,
    end_char INTEGER,
    metadata JSONB DEFAULT '{}'
);

-- Index for document chunk queries
CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_index ON document_chunks(document_id, chunk_index);

-- HNSW index for vector similarity search (cosine distance)
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
    ON document_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ============================================
-- PERSONAS TABLE
-- ============================================
-- Stores AI persona configurations

CREATE TABLE IF NOT EXISTS personas (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    system_prompt TEXT NOT NULL,
    voice_id VARCHAR(100),
    language VARCHAR(10) DEFAULT 'ko',
    is_active BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Default persona
INSERT INTO personas (name, description, system_prompt, is_active) VALUES
    ('EdgeVoice Assistant', 'Default EdgeVoice AI assistant',
     '당신은 EdgeVoice AI 어시스턴트입니다. 사용자의 질문에 친절하고 정확하게 답변해주세요.',
     true)
ON CONFLICT (name) DO NOTHING;

-- ============================================
-- AUDIT_LOG TABLE (Optional)
-- ============================================
-- Tracks changes to settings for debugging

CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(100) NOT NULL,
    record_key VARCHAR(255) NOT NULL,
    action VARCHAR(20) NOT NULL CHECK (action IN ('INSERT', 'UPDATE', 'DELETE')),
    old_value JSONB,
    new_value JSONB,
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    changed_by VARCHAR(100)
);

-- Index for audit queries
CREATE INDEX IF NOT EXISTS idx_audit_table_key ON audit_log(table_name, record_key);
CREATE INDEX IF NOT EXISTS idx_audit_changed_at ON audit_log(changed_at DESC);

-- ============================================
-- TRIGGERS
-- ============================================

-- Auto-update updated_at on settings changes
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_settings_updated_at ON settings;
CREATE TRIGGER update_settings_updated_at
    BEFORE UPDATE ON settings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_personas_updated_at ON personas;
CREATE TRIGGER update_personas_updated_at
    BEFORE UPDATE ON personas
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Auto-update last_active_at on new messages
CREATE OR REPLACE FUNCTION update_session_last_active()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE sessions SET last_active_at = NOW() WHERE id = NEW.session_id;
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_session_on_message ON messages;
CREATE TRIGGER update_session_on_message
    AFTER INSERT ON messages
    FOR EACH ROW
    EXECUTE FUNCTION update_session_last_active();

-- ============================================
-- GRANT PERMISSIONS
-- ============================================

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO edgevoice;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO edgevoice;

-- ============================================
-- SCHEMA VERSION
-- ============================================

CREATE TABLE IF NOT EXISTS schema_version (
    version VARCHAR(20) PRIMARY KEY,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    description TEXT
);

INSERT INTO schema_version (version, description) VALUES
    ('2.0.0', 'Phase 14: Database Architecture & Integration')
ON CONFLICT (version) DO NOTHING;

-- ============================================
-- PIPELINE_LOGS TABLE
-- ============================================
-- Stores pipeline execution logs for monitoring

CREATE TABLE IF NOT EXISTS pipeline_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
    service VARCHAR(50) NOT NULL,
    stage VARCHAR(100) NOT NULL,
    level VARCHAR(20) NOT NULL DEFAULT 'INFO' CHECK (level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR')),
    message TEXT NOT NULL,
    duration_ms INTEGER,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for efficient log queries
CREATE INDEX IF NOT EXISTS idx_pipeline_logs_created_at ON pipeline_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_logs_service ON pipeline_logs(service);
CREATE INDEX IF NOT EXISTS idx_pipeline_logs_level ON pipeline_logs(level);
CREATE INDEX IF NOT EXISTS idx_pipeline_logs_session_id ON pipeline_logs(session_id);

-- Composite index for filtering queries
CREATE INDEX IF NOT EXISTS idx_pipeline_logs_service_level ON pipeline_logs(service, level, created_at DESC);

-- Schema version for pipeline logs
INSERT INTO schema_version (version, description) VALUES
    ('2.1.0', 'Phase 17: Pipeline Logging System')
ON CONFLICT (version) DO NOTHING;
