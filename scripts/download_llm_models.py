"""
LLM Models Download Script

사용자가 요청한 10GB VRAM 이하 모델들을 다운로드합니다.
"""
import os
import sys
from pathlib import Path

# HuggingFace Hub
try:
    from huggingface_hub import snapshot_download, login
    from huggingface_hub.utils import HfHubHTTPError
except ImportError:
    print("huggingface_hub이 설치되지 않았습니다.")
    print("설치: pip install huggingface_hub")
    sys.exit(1)

# 모델 저장 경로
MODEL_CACHE_PATH = Path("c:/source/python/AI agent/models/llm/hub")

# 다운로드할 모델 목록 (10GB VRAM 이하)
MODELS_TO_DOWNLOAD = [
    # (HuggingFace repo ID, 표시 이름, 예상 크기, 필요 인증)
    ("Qwen/Qwen2.5-3B-Instruct", "Qwen 2.5 3B", "~6GB", False),
    ("microsoft/Phi-4-mini-instruct", "Phi-4 Mini", "~8GB", False),
    # qwen2.5-7b-instruct-awq는 이미 있음 - 스킵
    ("deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "DeepSeek R1 Qwen 7B", "~14GB", False),
    ("deepseek-ai/DeepSeek-R1-Distill-Llama-8B", "DeepSeek R1 Llama 8B", "~16GB", False),
    ("meta-llama/Llama-3.1-8B-Instruct", "Llama 3.1 8B", "~16GB", True),  # 인증 필요
    ("google/gemma-2-9b-it", "Gemma 2 9B", "~18GB", True),  # 인증 필요
    ("microsoft/phi-4", "Phi-4 14B", "~28GB", False),
    ("Qwen/Qwen2.5-14B-Instruct-AWQ", "Qwen 2.5 14B AWQ", "~8GB", False),
    ("deepseek-ai/DeepSeek-R1-Distill-Qwen-14B", "DeepSeek R1 Qwen 14B", "~28GB", False),
]


def check_hf_token():
    """HuggingFace 토큰 확인"""
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if token:
        print(f"✓ HF_TOKEN 환경변수 발견")
        return token

    # 토큰 파일 확인
    token_path = Path.home() / ".cache" / "huggingface" / "token"
    if token_path.exists():
        print(f"✓ HuggingFace 토큰 파일 발견: {token_path}")
        return token_path.read_text().strip()

    print("⚠ HuggingFace 토큰이 없습니다.")
    print("  일부 모델(Llama, Gemma)은 인증이 필요합니다.")
    print("  토큰 설정: huggingface-cli login")
    return None


def download_model(repo_id: str, display_name: str, size: str, requires_auth: bool, token: str = None):
    """단일 모델 다운로드"""
    print(f"\n{'='*60}")
    print(f"📥 다운로드 시작: {display_name}")
    print(f"   Repo: {repo_id}")
    print(f"   예상 크기: {size}")
    print(f"{'='*60}")

    if requires_auth and not token:
        print(f"⚠ 스킵: {display_name} - 인증 필요 (HF_TOKEN 없음)")
        return False

    try:
        local_dir = MODEL_CACHE_PATH / repo_id.replace("/", "--")

        # 이미 다운로드되었는지 확인
        if local_dir.exists() and any(local_dir.iterdir()):
            print(f"✓ 이미 존재함: {local_dir}")
            return True

        # 다운로드
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(local_dir),
            token=token,
            resume_download=True,  # 이어받기 지원
            local_dir_use_symlinks=False,
        )

        print(f"✓ 다운로드 완료: {display_name}")
        return True

    except HfHubHTTPError as e:
        if "401" in str(e) or "403" in str(e):
            print(f"✗ 인증 오류: {display_name}")
            print(f"  이 모델은 HuggingFace 라이선스 동의가 필요합니다.")
            print(f"  https://huggingface.co/{repo_id} 에서 라이선스에 동의해주세요.")
        else:
            print(f"✗ HTTP 오류: {e}")
        return False
    except Exception as e:
        print(f"✗ 다운로드 실패: {display_name}")
        print(f"  오류: {e}")
        return False


def main():
    print("="*60)
    print("EdgeVoice LLM 모델 다운로드 스크립트")
    print("10GB VRAM 이하 모델 (총 9개)")
    print("="*60)

    # 캐시 디렉토리 생성
    MODEL_CACHE_PATH.mkdir(parents=True, exist_ok=True)
    print(f"\n모델 저장 경로: {MODEL_CACHE_PATH}")

    # 토큰 확인
    token = check_hf_token()

    # 다운로드 결과 추적
    results = {
        "success": [],
        "skipped": [],
        "failed": []
    }

    print(f"\n총 {len(MODELS_TO_DOWNLOAD)}개 모델 다운로드 예정")
    print("(qwen2.5-7b-instruct-awq는 이미 있어서 제외됨)")

    for repo_id, display_name, size, requires_auth in MODELS_TO_DOWNLOAD:
        success = download_model(repo_id, display_name, size, requires_auth, token)

        if success:
            results["success"].append(display_name)
        elif requires_auth and not token:
            results["skipped"].append(display_name)
        else:
            results["failed"].append(display_name)

    # 결과 요약
    print("\n" + "="*60)
    print("다운로드 결과 요약")
    print("="*60)

    if results["success"]:
        print(f"\n✓ 성공 ({len(results['success'])}개):")
        for name in results["success"]:
            print(f"  - {name}")

    if results["skipped"]:
        print(f"\n⚠ 스킵 ({len(results['skipped'])}개) - 인증 필요:")
        for name in results["skipped"]:
            print(f"  - {name}")
        print("\n  인증이 필요한 모델 다운로드 방법:")
        print("  1. huggingface-cli login")
        print("  2. 각 모델 페이지에서 라이선스 동의")
        print("  3. 이 스크립트 다시 실행")

    if results["failed"]:
        print(f"\n✗ 실패 ({len(results['failed'])}개):")
        for name in results["failed"]:
            print(f"  - {name}")

    print("\n" + "="*60)
    print("완료!")
    print("="*60)


if __name__ == "__main__":
    main()
