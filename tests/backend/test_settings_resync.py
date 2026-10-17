"""
서비스가 다시 시작되면 저장한 설정을 다시 보낸다
(사용자 보고 2026-10-18: 설정이 저장이 안 된다)

실측: 설정은 DB 에 저장되지만, 서비스(컨테이너)만 다시 시작되면 기본값으로 돌아갔다
(무음 1.9초로 저장 → 게이트웨이 재시작 뒤 2.0초). 백엔드는 자기가 시작할 때만 보냈다.
→ 하트비트의 가동 시간이 줄면(또는 처음 보면) 그 서비스에 일반 설정을 다시 보낸다.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def test_watcher_notices_first_heartbeat_and_restart() -> None:
    from services.backend.app.services.settings_resync import RestartWatcher

    watcher = RestartWatcher()

    assert watcher.restarted("tts", 5) is True  # 처음 본다
    assert watcher.restarted("tts", 15) is False
    assert watcher.restarted("tts", 3) is True  # 가동 시간이 줄었다 — 다시 시작됨
    assert watcher.restarted("stt", 100) is True


def test_restarted_service_gets_its_saved_general_settings_again() -> None:
    from services.backend.app.routes import settings as settings_route
    from services.backend.app.services import settings_resync

    propagator = MagicMock(propagate=AsyncMock(return_value={"success": True}))
    saved = settings_route.GeneralSettings(wake_word_threshold=0.25)
    with (
        patch.object(settings_route, "_general_settings", saved),
        patch.object(
            settings_route, "get_settings_propagator", return_value=propagator
        ),
        patch.object(settings_resync, "_watcher", settings_resync.RestartWatcher()),
    ):
        asyncio.run(settings_resync.on_heartbeat("wake_word", {"uptime_seconds": 4}))
        asyncio.run(settings_resync.on_heartbeat("wake_word", {"uptime_seconds": 14}))

    propagator.propagate.assert_awaited_once_with(
        "wake_word", {"wake_word": "hey_jarvis", "threshold": 0.25}
    )


def test_heartbeat_without_settings_target_is_ignored() -> None:
    from services.backend.app.routes import settings as settings_route
    from services.backend.app.services import settings_resync

    propagator = MagicMock(propagate=AsyncMock())
    with (
        patch.object(
            settings_route, "get_settings_propagator", return_value=propagator
        ),
        patch.object(settings_resync, "_watcher", settings_resync.RestartWatcher()),
    ):
        asyncio.run(settings_resync.on_heartbeat("llm", {"proxy_uptime_seconds": 4}))
        asyncio.run(settings_resync.on_heartbeat("rag", {"uptime_seconds": 4}))

    propagator.propagate.assert_not_awaited()


def test_heartbeat_log_triggers_resync() -> None:
    from services.backend.app.routes import logs

    repo = MagicMock(create=AsyncMock(return_value="id"), get_by_id=AsyncMock())
    repo.get_by_id.return_value = {"id": "id"}
    log = logs.LogCreate(
        service="stt", stage="heartbeat", message="alive",
        metadata={"uptime_seconds": 3},
    )
    with (
        patch.object(logs, "PipelineLogRepository", return_value=repo),
        patch.object(logs, "broadcast_log", AsyncMock()),
        patch.object(logs, "on_heartbeat", AsyncMock()) as heartbeat,
    ):
        asyncio.run(logs.create_log(log))

    heartbeat.assert_called_once_with("stt", {"uptime_seconds": 3})
