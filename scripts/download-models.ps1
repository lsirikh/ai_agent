# ============================================
# EdgeVoice Model Download Script (PowerShell)
# ============================================
#
# Usage:
#   .\scripts\download-models.ps1 [-EnvType dev|jetson] [-Model all|stt|llm|tts|embedding|wakeword]
#
# Examples:
#   .\scripts\download-models.ps1                    # Download all dev models
#   .\scripts\download-models.ps1 -EnvType jetson   # Download jetson models
#   .\scripts\download-models.ps1 -Model stt        # Download STT only
# ============================================

param(
    [ValidateSet("dev", "jetson")]
    [string]$EnvType = "dev",

    [ValidateSet("all", "stt", "llm", "tts", "embedding", "wakeword")]
    [string]$Model = "all"
)

# Configuration
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$ModelDir = Join-Path $ProjectRoot "models"

# Model configurations based on environment
if ($EnvType -eq "jetson") {
    $STT_MODEL = "Systran/faster-whisper-small"
    $LLM_MODEL = "Qwen/Qwen2.5-7B-Instruct-GPTQ-Int4"
    $EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
} else {
    $STT_MODEL = "Systran/faster-whisper-large-v3"
    $LLM_MODEL = "Qwen/Qwen2.5-72B-Instruct-AWQ"
    $EMBEDDING_MODEL = "BAAI/bge-m3"
}

$TTS_MODEL = "hexgrad/Kokoro-82M"
$WAKEWORD_MODEL = "davidscripka/openwakeword"

# Colors
function Write-Header {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "  EdgeVoice Model Download" -ForegroundColor Cyan
    Write-Host "  Environment: $EnvType" -ForegroundColor Cyan
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step {
    param([string]$Message)
    Write-Host "[DOWNLOAD] " -ForegroundColor Green -NoNewline
    Write-Host $Message
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] " -ForegroundColor Green -NoNewline
    Write-Host $Message
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARNING] " -ForegroundColor Yellow -NoNewline
    Write-Host $Message
}

function Write-Err {
    param([string]$Message)
    Write-Host "[ERROR] " -ForegroundColor Red -NoNewline
    Write-Host $Message
}

function Test-HuggingFaceHub {
    try {
        $result = python -c "import huggingface_hub; print('ok')" 2>&1
        return $result -eq "ok"
    } catch {
        return $false
    }
}

function Install-HuggingFaceHub {
    Write-Step "Installing huggingface-hub..."
    python -m pip install huggingface-hub --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to install huggingface-hub"
        exit 1
    }
}

function Test-HFToken {
    # Check environment variable
    if ($env:HF_TOKEN) {
        Write-Success "HuggingFace token found in environment"
        return $true
    }

    # Check .env file
    $envFile = Join-Path $ProjectRoot ".env"
    if (Test-Path $envFile) {
        $content = Get-Content $envFile
        foreach ($line in $content) {
            if ($line -match "^HF_TOKEN=(.+)$") {
                $env:HF_TOKEN = $matches[1]
                Write-Success "HuggingFace token found in .env file"
                return $true
            }
        }
    }

    Write-Warn "HF_TOKEN not set. Some models may require authentication."
    Write-Host "Set HF_TOKEN in .env file or run: `$env:HF_TOKEN = 'your_token'"
    return $false
}

function Download-Model {
    param(
        [string]$ModelName,
        [string]$TargetDir,
        [string]$DisplayName
    )

    Write-Step "Downloading $DisplayName`: $ModelName"
    Write-Host "  Target: $TargetDir" -ForegroundColor Gray

    # Create target directory
    if (!(Test-Path $TargetDir)) {
        New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
    }

    # Build Python command
    $pythonCode = @"
import sys
from huggingface_hub import snapshot_download
import os

token = os.environ.get('HF_TOKEN', None)
try:
    snapshot_download(
        repo_id='$ModelName',
        local_dir=r'$TargetDir',
        local_dir_use_symlinks=False,
        token=token
    )
    print('SUCCESS')
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
"@

    try {
        $result = python -c $pythonCode 2>&1

        if ($LASTEXITCODE -eq 0) {
            Write-Success "$DisplayName downloaded successfully"
            return $true
        } else {
            Write-Warn "Download issue: $result"
            return $false
        }
    } catch {
        Write-Warn "Failed to download $DisplayName`: $_"
        return $false
    }
}

function Download-STT {
    $targetDir = Join-Path $ModelDir "whisper"
    Download-Model -ModelName $STT_MODEL -TargetDir $targetDir -DisplayName "STT (Whisper)"
}

function Download-LLM {
    Write-Warn "LLM model is very large (~40GB). This may take a long time..."
    $targetDir = Join-Path $ModelDir "llm"
    Download-Model -ModelName $LLM_MODEL -TargetDir $targetDir -DisplayName "LLM (Qwen)"
}

function Download-TTS {
    $targetDir = Join-Path $ModelDir "kokoro"
    Download-Model -ModelName $TTS_MODEL -TargetDir $targetDir -DisplayName "TTS (Kokoro)"
}

function Download-Embedding {
    $targetDir = Join-Path $ModelDir "embedding"
    Download-Model -ModelName $EMBEDDING_MODEL -TargetDir $targetDir -DisplayName "Embedding (BGE)"
}

function Download-WakeWord {
    $targetDir = Join-Path $ModelDir "openwakeword"
    Download-Model -ModelName $WAKEWORD_MODEL -TargetDir $targetDir -DisplayName "Wake Word"
}

function Show-Summary {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  Model Download Summary" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Environment: $EnvType"
    Write-Host ""
    Write-Host "Models:"
    Write-Host "  - STT: $STT_MODEL"
    Write-Host "  - LLM: $LLM_MODEL"
    Write-Host "  - TTS: $TTS_MODEL"
    Write-Host "  - Embedding: $EMBEDDING_MODEL"
    Write-Host "  - Wake Word: $WAKEWORD_MODEL"
    Write-Host ""
    Write-Host "Model directory: $ModelDir"

    if (Test-Path $ModelDir) {
        $files = Get-ChildItem $ModelDir -Recurse -File -ErrorAction SilentlyContinue
        if ($files) {
            $size = ($files | Measure-Object -Property Length -Sum).Sum
            if ($size) {
                $sizeGB = [math]::Round($size / 1GB, 2)
                Write-Host "Total size: ${sizeGB} GB"
            }
        } else {
            Write-Host "Total size: 0 GB (no files downloaded yet)"
        }
    }
    Write-Host ""
}

function Show-Menu {
    Write-Host ""
    Write-Host "Select models to download:"
    Write-Host "  1) All models (recommended for full setup)"
    Write-Host "  2) STT only (Whisper) - ~3GB"
    Write-Host "  3) LLM only (Qwen) - ~40GB (very large!)"
    Write-Host "  4) TTS only (Kokoro) - ~200MB"
    Write-Host "  5) Embedding only (BGE) - ~2GB"
    Write-Host "  6) Wake Word only - ~50MB"
    Write-Host "  0) Cancel"
    Write-Host ""

    $choice = Read-Host "Enter your choice [1]"
    if ([string]::IsNullOrEmpty($choice)) { $choice = "1" }

    switch ($choice) {
        "1" {
            Download-STT
            Download-TTS
            Download-Embedding
            Download-WakeWord
            Write-Host ""
            Write-Warn "Skipping LLM download (very large). Run with -Model llm to download separately."
        }
        "2" { Download-STT }
        "3" { Download-LLM }
        "4" { Download-TTS }
        "5" { Download-Embedding }
        "6" { Download-WakeWord }
        "0" {
            Write-Host "Download cancelled."
            exit 0
        }
        default {
            Write-Err "Invalid choice"
            exit 1
        }
    }
}

# Main
Write-Header

# Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "Python: $pythonVersion" -ForegroundColor Gray
} catch {
    Write-Err "Python not found. Please install Python 3.8+"
    exit 1
}

# Check huggingface-hub
if (!(Test-HuggingFaceHub)) {
    Install-HuggingFaceHub
}

# Check HF token
Test-HFToken | Out-Null

# Create model directory
if (!(Test-Path $ModelDir)) {
    New-Item -ItemType Directory -Path $ModelDir -Force | Out-Null
    Write-Host "Created model directory: $ModelDir" -ForegroundColor Gray
}

# Download based on -Model parameter
switch ($Model) {
    "all" { Show-Menu }
    "stt" { Download-STT }
    "llm" { Download-LLM }
    "tts" { Download-TTS }
    "embedding" { Download-Embedding }
    "wakeword" { Download-WakeWord }
}

Show-Summary
