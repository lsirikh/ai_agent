"""
Phase 33.1: LLM Loading Progress Parser
Docker logs에서 vLLM 모델 로딩 진행률을 파싱합니다.

Phase 33.2.2: Pipeline Log 통합
LLM 로딩 진행률을 Pipeline Log에 기록합니다.
"""

import asyncio
import re
from typing import Optional

from .pipeline_logger import get_logger


def parse_vllm_progress(log_text: str) -> Optional[dict]:
    """
    vLLM Docker 로그에서 진행률 정보를 파싱합니다.

    Args:
        log_text: Docker 로그 텍스트

    Returns:
        진행률 정보 딕셔너리 또는 None
        {
            "progress_percent": int (0-100),
            "stage": str ("initializing" | "loading_weights" | "complete"),
            "message": str
        }
    """
    if not log_text:
        return None

    # 패턴 1: 모델 로딩 완료
    # "Model loaded successfully" 또는 유사 패턴
    if "loaded successfully" in log_text.lower() or "model loaded" in log_text.lower():
        return {
            "progress_percent": 100,
            "stage": "complete",
            "message": "Model loaded successfully"
        }

    # 패턴 2: 모델 가중치 로딩 진행률
    # "Loading model weights:  45%|████" 패턴 파싱
    weight_pattern = r"Loading model weights:\s*(\d+)%"
    match = re.search(weight_pattern, log_text)
    if match:
        percent = int(match.group(1))
        return {
            "progress_percent": percent,
            "stage": "loading_weights",
            "message": f"Loading model weights: {percent}%"
        }

    # 패턴 3: 초기화 단계
    # "Initializing" 패턴 감지
    if "initializing" in log_text.lower():
        return {
            "progress_percent": 0,
            "stage": "initializing",
            "message": "Initializing the model"
        }

    # 알 수 없는 패턴
    return None


async def get_docker_logs(container_name: str, tail_lines: int = 50) -> str:
    """
    Docker 컨테이너 로그를 조회합니다.

    Args:
        container_name: Docker 컨테이너 이름
        tail_lines: 조회할 최근 로그 라인 수 (기본: 50)

    Returns:
        컨테이너 로그 문자열 (에러 시 빈 문자열)
    """
    try:
        # docker logs 명령 실행
        process = await asyncio.create_subprocess_exec(
            "docker", "logs", "--tail", str(tail_lines), container_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        # stdout과 stderr 모두 확인 (vLLM은 stderr에 진행률 출력)
        logs = stdout.decode("utf-8", errors="ignore")
        if stderr:
            logs += stderr.decode("utf-8", errors="ignore")

        return logs

    except Exception as e:
        # Docker 실행 실패 시 빈 문자열 반환
        return ""


async def get_llm_loading_progress(container_name: str) -> dict:
    """
    LLM 컨테이너의 로딩 진행률을 조회합니다.

    Docker logs를 파싱하여 진행률을 추출하고,
    파싱 실패 시 기본값을 반환합니다.

    Args:
        container_name: LLM Docker 컨테이너 이름 (예: "vllm")

    Returns:
        진행률 정보 딕셔너리
        {
            "progress_percent": int (0-100),
            "stage": str ("unknown" | "initializing" | "loading_weights" | "complete"),
            "message": str
        }
    """
    # 기본값 (파싱 실패 시)
    default_result = {
        "progress_percent": 0,
        "stage": "unknown",
        "message": "Unable to determine loading progress"
    }

    try:
        # Docker 로그 조회
        logs = await get_docker_logs(container_name, tail_lines=100)

        if not logs:
            return default_result

        # 로그를 줄 단위로 역순으로 파싱 (최근 로그 우선)
        lines = logs.strip().split("\n")
        for line in reversed(lines):
            result = parse_vllm_progress(line)
            if result:
                return result

        return default_result

    except Exception as e:
        return default_result


async def log_llm_loading_progress(
    progress_percent: int,
    stage: str,
    message: str,
    session_id: Optional[str] = None
) -> None:
    """
    Phase 33.2.2: LLM 로딩 진행률을 Pipeline Log에 기록합니다.

    Args:
        progress_percent: 진행률 (0-100)
        stage: 로딩 단계 ("initializing" | "loading_weights" | "complete")
        message: 로그 메시지
        session_id: 세션 ID (옵션)
    """
    logger = get_logger("orchestrator")
    await logger.log(
        event="llm_loading_progress",
        session_id=session_id,
        data={
            "progress_percent": progress_percent,
            "stage": stage,
            "message": message
        }
    )