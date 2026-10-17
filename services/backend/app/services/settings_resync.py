"""
서비스가 다시 시작되면 저장한 일반 설정을 다시 보낸다.

설정은 DB 에 저장되지만 서비스(컨테이너)만 다시 시작되면 기본값으로 돌아갔다
(실측: 무음 1.9초로 저장 → 게이트웨이 재시작 뒤 2.0초). 서비스는 10초마다
하트비트(가동 시간)를 로그로 보내므로, 가동 시간이 줄었거나 처음 보면 다시 보낸다.
"""

from typing import Any, Dict, Optional


class RestartWatcher:
    def __init__(self) -> None:
        self._uptime: Dict[str, float] = {}

    def restarted(self, service: str, uptime: float) -> bool:
        """처음 보거나 가동 시간이 줄었으면(다시 시작됨) True."""
        last = self._uptime.get(service)
        self._uptime[service] = uptime
        return last is None or uptime < last


_watcher = RestartWatcher()


async def on_heartbeat(service: str, metadata: Optional[Dict[str, Any]]) -> None:
    """하트비트 로그 하나. 다시 시작된 서비스면 그 서비스가 받는 일반 설정을 보낸다."""
    from ..routes import settings as settings_route

    uptime = (metadata or {}).get("uptime_seconds")
    targets = settings_route.general_settings_by_service(
        settings_route._general_settings
    )
    if uptime is None or service not in targets:
        return
    if not _watcher.restarted(service, float(uptime)):
        return
    try:
        propagator = settings_route.get_settings_propagator()
        await propagator.propagate(service, targets[service])
    except Exception as e:
        print(f"[Settings] {service} 설정 다시 보내기 실패: {e}")
