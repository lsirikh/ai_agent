"""
Unified Health Check Utility
Phase 30.4: Health Check 통합

HTTP Health Check를 수행하는 통합 유틸리티.
"""
import time
from typing import Dict, Any, Optional

import httpx


async def check_health(
    url: str,
    timeout: float = 2.0,
    expect_json: bool = False
) -> Dict[str, Any]:
    """
    HTTP Health Check 수행

    Args:
        url: Health check URL
        timeout: 타임아웃 (초)
        expect_json: True면 JSON 응답 파싱

    Returns:
        Dict with keys:
            - healthy: bool
            - latency_ms: float
            - error: str (unhealthy인 경우)
            - data: dict (expect_json=True이고 healthy인 경우)
    """
    start = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            latency_ms = (time.perf_counter() - start) * 1000

            if response.status_code == 200:
                result = {
                    "healthy": True,
                    "latency_ms": latency_ms
                }

                if expect_json and response.content:
                    result["data"] = response.json()

                return result
            else:
                return {
                    "healthy": False,
                    "latency_ms": latency_ms,
                    "error": f"HTTP {response.status_code}"
                }

    except httpx.TimeoutException:
        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "healthy": False,
            "latency_ms": latency_ms,
            "error": "timeout"
        }

    except httpx.ConnectError:
        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "healthy": False,
            "latency_ms": latency_ms,
            "error": "connection_refused"
        }

    except Exception as e:
        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "healthy": False,
            "latency_ms": latency_ms,
            "error": str(e)
        }