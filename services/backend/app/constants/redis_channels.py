"""
Redis Channel Constants
Phase 30.5: Redis 채널 상수 통합

모든 서비스에서 사용하는 Redis Pub/Sub 채널 이름을 정의합니다.
"""


class RedisChannels:
    """Redis Pub/Sub 채널 상수"""

    # Orchestrator 상태 브로드캐스트 채널
    ORCHESTRATOR_STATE = "edgevoice:orchestrator:state"

    # 파이프라인 로그 채널
    PIPELINE_LOGS = "edgevoice:logs:pipeline"

    # 설정 브로드캐스트 채널
    SETTINGS_BROADCAST = "edgevoice:settings:broadcast"

    # 대화 메시지 저장 알림 채널 (/api/chat/stream 이 구독)
    CHAT_MESSAGE = "edgevoice:chat:message"

    # 대시보드 업데이트 채널
    DASHBOARD_UPDATES = "dashboard:updates"

    # 설정 타입별 채널
    SETTINGS_TTS = "settings:tts"
    SETTINGS_STT = "settings:stt"
    SETTINGS_LLM = "settings:llm"
    SETTINGS_AUDIO = "settings:audio"