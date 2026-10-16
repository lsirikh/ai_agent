"""
LLM Models Batch Download Script
사용자 요청: 10GB VRAM 이하 모델 전체 다운로드
"""
import os
import sys
from pathlib import Path
from datetime import datetime

try:
    from huggingface_hub import snapshot_download
except ImportError:
    print("huggingface_hub이 설치되지 않았습니다.")
    sys.exit(1)

# 모델 저장 경로
CACHE_PATH = Path("c:/source/python/AI agent/models/llm/hub")
CACHE_PATH.mkdir(parents=True, exist_ok=True)

# 다운로드할 모델 목록
MODELS = [
    ("Qwen/Qwen2.5-3B-Instruct", "Qwen 2.5 3B", "~6GB"),
    ("microsoft/Phi-4-mini-instruct", "Phi-4 Mini", "~8GB"),
    ("deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "DeepSeek R1 Qwen 7B", "~14GB"),
    ("deepseek-ai/DeepSeek-R1-Distill-Llama-8B", "DeepSeek R1 Llama 8B", "~16GB"),
    ("meta-llama/Llama-3.1-8B-Instruct", "Llama 3.1 8B", "~16GB"),
    ("google/gemma-2-9b-it", "Gemma 2 9B", "~18GB"),
    ("microsoft/phi-4", "Phi-4 14B", "~28GB"),
    ("Qwen/Qwen2.5-14B-Instruct-AWQ", "Qwen 2.5 14B AWQ", "~8GB"),
    ("deepseek-ai/DeepSeek-R1-Distill-Qwen-14B", "DeepSeek R1 Qwen 14B", "~28GB"),
]

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)

def download_model(repo_id, name, size):
    log(f"=== 다운로드 시작: {name} ({size}) ===")
    local_dir = CACHE_PATH / repo_id.replace("/", "--")

    if local_dir.exists() and any(local_dir.glob("*.safetensors")):
        log(f"✓ 이미 존재함: {name}")
        return True

    try:
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(local_dir)
        )
        log(f"✓ 완료: {name}")
        return True
    except Exception as e:
        log(f"✗ 실패: {name} - {e}")
        return False

def main():
    log("="*60)
    log("EdgeVoice LLM 모델 다운로드 시작")
    log(f"총 {len(MODELS)}개 모델")
    log("="*60)

    results = {"success": [], "failed": []}

    for repo_id, name, size in MODELS:
        if download_model(repo_id, name, size):
            results["success"].append(name)
        else:
            results["failed"].append(name)

    log("\n" + "="*60)
    log("다운로드 완료 요약")
    log(f"성공: {len(results['success'])}개")
    log(f"실패: {len(results['failed'])}개")
    if results["failed"]:
        log(f"실패 목록: {results['failed']}")
    log("="*60)

if __name__ == "__main__":
    main()
