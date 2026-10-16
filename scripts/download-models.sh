#!/bin/bash
# ============================================
# EdgeVoice Model Download Script
# Phase 7.3: 모델 다운로드 스크립트
# ============================================
#
# Usage:
#   ./scripts/download-models.sh [dev|jetson]
#
# Models downloaded:
#   - STT: Faster-Whisper (large-v3 or small)
#   - LLM: Qwen2.5 (72B-AWQ or 7B-GPTQ)
#   - TTS: Kokoro 82M
#   - Embedding: BGE-M3 or BGE-Small
#   - Wake Word: OpenWakeWord
# ============================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_TYPE="${1:-dev}"
MODEL_DIR="$PROJECT_ROOT/models"

# Model configurations
if [ "$ENV_TYPE" = "jetson" ]; then
    STT_MODEL="Systran/faster-whisper-small"
    LLM_MODEL="Qwen/Qwen2.5-7B-Instruct-GPTQ-Int4"
    EMBEDDING_MODEL="BAAI/bge-small-en-v1.5"
else
    STT_MODEL="Systran/faster-whisper-large-v3"
    LLM_MODEL="Qwen/Qwen2.5-72B-Instruct-AWQ"
    EMBEDDING_MODEL="BAAI/bge-m3"
fi

print_header() {
    echo -e "${BLUE}"
    echo "============================================"
    echo "  EdgeVoice Model Download"
    echo "  Environment: $ENV_TYPE"
    echo "============================================"
    echo -e "${NC}"
}

print_step() {
    echo -e "${GREEN}[DOWNLOAD]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

check_huggingface_cli() {
    if ! command -v huggingface-cli &> /dev/null; then
        print_step "Installing huggingface-hub..."
        pip install huggingface-hub
    fi
}

check_hf_token() {
    if [ -z "$HF_TOKEN" ]; then
        if [ -f "$PROJECT_ROOT/.env" ]; then
            source "$PROJECT_ROOT/.env"
        fi
    fi

    if [ -z "$HF_TOKEN" ]; then
        print_warning "HF_TOKEN not set. Some models may require authentication."
        echo "Set HF_TOKEN in .env file or export HF_TOKEN=your_token"
    else
        print_success "HuggingFace token found"
        export HUGGING_FACE_HUB_TOKEN="$HF_TOKEN"
    fi
}

download_stt_model() {
    print_step "Downloading STT model: $STT_MODEL"

    local model_path="$MODEL_DIR/whisper"
    mkdir -p "$model_path"

    # Download using huggingface-cli
    huggingface-cli download "$STT_MODEL" \
        --local-dir "$model_path" \
        --local-dir-use-symlinks False \
        2>&1 || {
            print_warning "Failed to download STT model. It will be downloaded on first run."
        }

    if [ -d "$model_path" ] && [ "$(ls -A $model_path)" ]; then
        print_success "STT model downloaded to $model_path"
    fi
}

download_llm_model() {
    print_step "Downloading LLM model: $LLM_MODEL"
    print_warning "This may take a long time depending on your connection speed..."

    local model_path="$MODEL_DIR/llm"
    mkdir -p "$model_path"

    # Download using huggingface-cli
    huggingface-cli download "$LLM_MODEL" \
        --local-dir "$model_path" \
        --local-dir-use-symlinks False \
        2>&1 || {
            print_warning "Failed to download LLM model. It will be downloaded on first run."
        }

    if [ -d "$model_path" ] && [ "$(ls -A $model_path)" ]; then
        print_success "LLM model downloaded to $model_path"
    fi
}

download_tts_model() {
    print_step "Downloading TTS model: Kokoro"

    local model_path="$MODEL_DIR/kokoro"
    mkdir -p "$model_path"

    # Kokoro model download
    # Note: Actual model URL may vary
    huggingface-cli download "hexgrad/Kokoro-82M" \
        --local-dir "$model_path" \
        --local-dir-use-symlinks False \
        2>&1 || {
            print_warning "Failed to download TTS model. It will be downloaded on first run."
        }

    if [ -d "$model_path" ] && [ "$(ls -A $model_path)" ]; then
        print_success "TTS model downloaded to $model_path"
    fi
}

download_embedding_model() {
    print_step "Downloading Embedding model: $EMBEDDING_MODEL"

    local model_path="$MODEL_DIR/embedding"
    mkdir -p "$model_path"

    huggingface-cli download "$EMBEDDING_MODEL" \
        --local-dir "$model_path" \
        --local-dir-use-symlinks False \
        2>&1 || {
            print_warning "Failed to download Embedding model. It will be downloaded on first run."
        }

    if [ -d "$model_path" ] && [ "$(ls -A $model_path)" ]; then
        print_success "Embedding model downloaded to $model_path"
    fi
}

download_wakeword_model() {
    print_step "Downloading Wake Word model: OpenWakeWord"

    local model_path="$MODEL_DIR/openwakeword"
    mkdir -p "$model_path"

    # OpenWakeWord models
    huggingface-cli download "davidscripka/openwakeword" \
        --local-dir "$model_path" \
        --local-dir-use-symlinks False \
        2>&1 || {
            print_warning "Failed to download Wake Word model. It will be downloaded on first run."
        }

    if [ -d "$model_path" ] && [ "$(ls -A $model_path)" ]; then
        print_success "Wake Word model downloaded to $model_path"
    fi
}

print_summary() {
    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}  Model Download Summary${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo "Environment: $ENV_TYPE"
    echo ""
    echo "Models:"
    echo "  - STT: $STT_MODEL"
    echo "  - LLM: $LLM_MODEL"
    echo "  - TTS: Kokoro-82M"
    echo "  - Embedding: $EMBEDDING_MODEL"
    echo "  - Wake Word: OpenWakeWord"
    echo ""
    echo "Model directory: $MODEL_DIR"
    echo ""

    # Calculate total size
    if [ -d "$MODEL_DIR" ]; then
        total_size=$(du -sh "$MODEL_DIR" 2>/dev/null | cut -f1)
        echo "Total size: $total_size"
    fi
    echo ""
}

select_models() {
    echo ""
    echo "Select models to download:"
    echo "  1) All models (recommended)"
    echo "  2) STT only (Whisper)"
    echo "  3) LLM only (Qwen)"
    echo "  4) TTS only (Kokoro)"
    echo "  5) Embedding only (BGE)"
    echo "  6) Wake Word only (OpenWakeWord)"
    echo "  0) Cancel"
    echo ""
    read -p "Enter your choice [1]: " choice
    choice=${choice:-1}

    case $choice in
        1)
            download_stt_model
            download_llm_model
            download_tts_model
            download_embedding_model
            download_wakeword_model
            ;;
        2)
            download_stt_model
            ;;
        3)
            download_llm_model
            ;;
        4)
            download_tts_model
            ;;
        5)
            download_embedding_model
            ;;
        6)
            download_wakeword_model
            ;;
        0)
            echo "Download cancelled."
            exit 0
            ;;
        *)
            print_error "Invalid choice"
            exit 1
            ;;
    esac
}

main() {
    print_header

    # Validate environment type
    if [ "$ENV_TYPE" != "dev" ] && [ "$ENV_TYPE" != "jetson" ]; then
        print_error "Invalid environment type: $ENV_TYPE"
        echo "Usage: $0 [dev|jetson]"
        exit 1
    fi

    check_huggingface_cli
    check_hf_token

    # Create model directory
    mkdir -p "$MODEL_DIR"

    # Interactive model selection
    if [ -t 0 ]; then
        select_models
    else
        # Non-interactive: download all
        download_stt_model
        download_llm_model
        download_tts_model
        download_embedding_model
        download_wakeword_model
    fi

    print_summary
}

main "$@"
