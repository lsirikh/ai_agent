# EdgeVoice 파이프라인 로깅 분석 보고서

> **작성일**: 2025-12-12
> **분석 대상**: Dashboard Service Status 및 Pipeline Logs 기능

---

## 목차

1. [문제 요약](#1-문제-요약)
2. [Health 로그 DB 저장 문제](#2-health-로그-db-저장-문제)
3. [서비스별 로깅 구현 현황](#3-서비스별-로깅-구현-현황)
4. [핵심 원인 분석](#4-핵심-원인-분석)
5. [수정 권장사항](#5-수정-권장사항)
6. [파일 위치 참조](#6-파일-위치-참조)
7. [Redis 채널 상수 상세 분석](#7-redis-채널-상수-상세-분석)

---

## 1. 문제 요약

### 발견된 문제점

| 문제 | 증상 | 심각도 | 상태 |
|------|------|--------|------|
| ~~Pipeline Logs 미저장~~ | ~~Health 로그가 DB에 저장되지 않음~~ | ~~CRITICAL~~ | ✅ **해결됨** |
| ~~Redis 채널 불일치~~ | ~~Broadcaster와 Subscriber가 다른 채널 사용~~ | ~~CRITICAL~~ | ✅ **해결됨** |

### 핵심 발견

1. ~~**Health 체크 결과가 pipeline_logs 테이블에 저장되지 않음**~~ - ✅ **해결됨** (Phase 31.3: log_subscriber.py에 DB 저장 로직 추가)
2. ~~**Redis 채널 이름 불일치**~~ - ✅ **해결됨** (Phase 31.2: log_broadcaster.py 수정 완료)

---

## 2. Health 로그 DB 저장 문제

### 2.1 시스템 아키텍처

```
┌────────────────────────────────────────────────────────────────────┐
│                    설계된 로그 플로우                               │
└────────────────────────────────────────────────────────────────────┘

Services (STT, TTS, LLM, etc.)
         │
         │ Redis Pub/Sub
         ▼
edgevoice:logs:pipeline 채널
         │
         ▼
LogSubscriber.listen()
         │
         ▼
PipelineLogRepository.create()
         │
         ▼
PostgreSQL pipeline_logs 테이블
         │
         ▼
LogBroadcaster.broadcast()
         │
         │ Redis Pub/Sub
         ▼
edgevoice:logs 채널
         │
         ▼
SSE /api/logs/stream
         │
         ▼
Dashboard > Pipeline Logs 표시
```

### 2.2 발견된 핵심 문제

#### ~~문제 #1: Redis 채널 불일치~~ ✅ **해결됨**

**파일: `services/backend/app/services/log_broadcaster.py`** - **수정 완료**
```python
# Phase 31.2: 채널 통합 (edgevoice:logs -> edgevoice:logs:pipeline)
from ..constants.redis_channels import RedisChannels

# Redis 로그 채널 (log_subscriber.py와 동일)
LOGS_CHANNEL = RedisChannels.PIPELINE_LOGS  # "edgevoice:logs:pipeline" ✅
```

**파일: `services/backend/app/services/log_subscriber.py`**
```python
# Line 19
LOGS_CHANNEL = RedisChannels.PIPELINE_LOGS  # ← "edgevoice:logs:pipeline" ✅
```

**결과**: Broadcaster와 Subscriber가 동일한 채널(`edgevoice:logs:pipeline`)을 사용 → **채널 통일 완료**

#### ~~문제 #2: LogSubscriber DB 저장 로직 누락~~ ✅ **해결됨**

**파일: `services/backend/app/services/log_subscriber.py`** - **Phase 31.3에서 수정 완료**

```python
# LogSubscriber.listen() 메서드 - 수정됨
async def listen(self):
    # Phase 31.3: DB 저장을 위한 Repository 인스턴스
    repo = PipelineLogRepository()

    async for message in self._pubsub.listen():
        if message["type"] == "message":
            log_data = json.loads(data)

            # Phase 31.3: DB에 로그 저장 ✅
            await self._save_log_to_db(repo, log_data)

            if self._on_log:
                await self._on_log(log_data)
```

**추가된 메서드**: `_save_log_to_db()` - PipelineLogger 형식의 로그를 DB 스키마에 맞게 변환하여 저장

### 2.3 LogSubscriber 아키텍처 분석

#### 현재 구현 상태

**시작 위치**: `services/backend/app/main.py`

```python
# Line 38-54: Log Subscriber 시작
async def start_log_subscriber():
    global _log_subscriber, _log_subscriber_task
    _log_subscriber = LogSubscriber()  # ← on_log 콜백 없이 생성
    await _log_subscriber.subscribe()
    _log_subscriber_task = asyncio.create_task(_log_subscriber.listen())
```

**문제점**: `LogSubscriber()`가 `on_log` 콜백 없이 생성되어 `listen()`에서 DB 저장이 불가능

#### DB 저장이 일어나는 유일한 곳

**파일**: `services/backend/app/routes/logs.py` - `POST /api/logs` 엔드포인트

```python
# Line 260-299: create_log() - HTTP API로 로그 생성 시에만 DB 저장
@router.post("", response_model=LogResponse, status_code=201)
async def create_log(log: LogCreate):
    repo = PipelineLogRepository()
    log_id = await repo.create(...)  # ← 여기서만 DB 저장!
    await broadcast_log(created_log)  # Redis로 브로드캐스트
    return created_log
```

#### 데이터 흐름 비교

| 경로 | 발생 조건 | DB 저장 | 동작 |
|------|----------|---------|------|
| **서비스 하트비트** | 10초마다 자동 | ❌ | `PipelineLogger.info()` → Redis pub → LogSubscriber 수신 → 콜백만 호출 |
| **POST /api/logs** | HTTP API 호출 시 | ✅ | API 요청 → `repo.create()` → DB 저장 → Redis pub |

**결론**: 서비스들이 발행하는 하트비트 로그는 Redis Pub/Sub를 통해 전달되지만, `LogSubscriber`에서 DB 저장 로직이 없어서 `pipeline_logs` 테이블에 저장되지 않음

#### 수정해야 할 위치

**Option A**: `log_subscriber.py`의 `listen()` 메서드에 DB 저장 추가

```python
# services/backend/app/services/log_subscriber.py - listen() 수정
from ..repositories.pipeline_log_repository import PipelineLogRepository

async def listen(self):
    repo = PipelineLogRepository()  # ← 추가

    async for message in self._pubsub.listen():
        if message["type"] == "message":
            log_data = json.loads(data)

            # DB 저장 추가
            await repo.create(
                service=log_data.get("service", "unknown"),
                stage=log_data.get("event", "general"),
                message=log_data.get("data", {}).get("message", ""),
                level=log_data.get("level", "INFO"),
                ...
            )

            if self._on_log:
                await self._on_log(log_data)
```

**Option B**: `main.py`에서 `LogSubscriber` 생성 시 콜백 주입

```python
# services/backend/app/main.py - start_log_subscriber() 수정
async def save_log_to_db(log_data: dict):
    repo = PipelineLogRepository()
    await repo.create(...)

async def start_log_subscriber():
    _log_subscriber = LogSubscriber(on_log=save_log_to_db)  # ← 콜백 주입
    ...
```

### 2.4 데이터베이스 스키마 확인

**파일: `config/postgres/init.sql`**

```sql
-- Lines 246-275: pipeline_logs 테이블
CREATE TABLE IF NOT EXISTS pipeline_logs (
    id SERIAL PRIMARY KEY,
    session_id UUID,
    service VARCHAR(50) NOT NULL,
    stage VARCHAR(50) NOT NULL,
    level VARCHAR(20) DEFAULT 'INFO',
    message TEXT NOT NULL,
    duration_ms FLOAT,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 (성능 문제 관련)
CREATE INDEX IF NOT EXISTS idx_pipeline_logs_created_at ON pipeline_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_logs_service ON pipeline_logs(service);
CREATE INDEX IF NOT EXISTS idx_pipeline_logs_level ON pipeline_logs(level);
CREATE INDEX IF NOT EXISTS idx_pipeline_logs_session_id ON pipeline_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_logs_service_created
    ON pipeline_logs(service, created_at DESC);
```

### 2.5 기대 동작 vs 실제 동작

| 단계 | 기대 동작 | 실제 동작 |
|------|----------|----------|
| 1 | 서비스 하트비트 발행 | ✅ 정상 |
| 2 | Redis 채널로 전송 | ✅ 정상 (채널 통일됨) |
| 3 | LogSubscriber가 수신 | ✅ 정상 |
| 4 | `PipelineLogRepository.create()` 호출 | ❌ **누락** |
| 5 | DB에 로그 저장 | ❌ 저장 안됨 |
| 6 | Dashboard에서 조회 | ❌ 빈 목록 |

---

## 3. 서비스별 로깅 구현 현황

### 3.1 로깅 아키텍처 설계 원안 (Agenda)

**목표**:
- 각 서비스는 자체 헬스 상태와 파이프라인 Phase 정보를 Redis로 발행
- 모든 서비스가 동일한 채널(`edgevoice:logs:pipeline`)로 로그 전송
- Backend가 Redis 구독하여 DB 저장 + Dashboard SSE 스트리밍

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       설계된 로깅 아키텍처                                    │
└─────────────────────────────────────────────────────────────────────────────┘

┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐
│    STT    │  │    TTS    │  │Orchestrator│  │Wake Word │  │Audio GW   │
│  Service  │  │  Service  │  │  Service   │  │ Service  │  │  Service  │
└─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘
      │              │              │              │              │
      │  PipelineLogger.info("heartbeat", ...)   │              │
      │  10초 주기 하트비트                        │              │
      │              │              │              │              │
      └──────────────┴──────────────┴──────────────┴──────────────┘
                                    │
                                    ▼
                     ┌──────────────────────────────┐
                     │   Redis Pub/Sub              │
                     │   edgevoice:logs:pipeline    │
                     └──────────────┬───────────────┘
                                    │
                                    ▼
                     ┌──────────────────────────────┐
                     │   Backend LogSubscriber      │
                     │   - DB 저장                   │
                     │   - SSE 브로드캐스트          │
                     └──────────────┬───────────────┘
                                    │
                     ┌──────────────┴───────────────┐
                     ▼                              ▼
          ┌─────────────────────┐       ┌─────────────────────┐
          │  PostgreSQL         │       │  Dashboard SSE      │
          │  pipeline_logs 테이블│       │  /api/logs/stream   │
          └─────────────────────┘       └─────────────────────┘
```

### 3.2 서비스별 Health 로그 송신 코드

#### ✅ STT Service

**파일**: `services/stt/app/main.py:44-67`

```python
async def heartbeat_task() -> None:
    """하트비트 로그 태스크 (10초 간격)"""
    global _heartbeat_running
    _heartbeat_running = True

    while _heartbeat_running:
        uptime_seconds = int(time.time() - _service_start_time)
        await _logger.info(
            "heartbeat",
            f"STT Service alive (uptime: {uptime_seconds}s)",
            metadata={
                "service": "stt",
                "uptime_seconds": uptime_seconds,
                "model": MODEL_SIZE,
                "device": DEVICE,
                "transcription_count": _transcription_count
            }
        )
        await asyncio.sleep(HEARTBEAT_INTERVAL)  # 10초
```

**시작 위치**: `services/stt/app/main.py:89`
```python
asyncio.create_task(heartbeat_task())
```

---

#### ✅ TTS Service

**파일**: `services/tts/app/main.py:33-46`

```python
async def heartbeat_loop():
    """Phase 27.7: 주기적으로 heartbeat 로그 전송"""
    logger = get_logger("tts")
    while True:
        try:
            uptime = int(time.time() - _start_time)
            await logger.info(
                "heartbeat",
                f"TTS Service alive (uptime: {uptime}s)",
                metadata={
                    "uptime_seconds": uptime,
                    "engine": _current_settings.get("engine", "unknown")
                }
            )
        except Exception as e:
            print(f"[TTS] Heartbeat failed: {e}")
        await asyncio.sleep(10)  # 10초마다
```

**시작 위치**: `services/tts/app/main.py:77`
```python
_heartbeat_task = asyncio.create_task(heartbeat_loop())
```

---

#### ✅ Orchestrator Service

**파일**: `services/orchestrator/app/main.py:36-62`

```python
async def heartbeat_task() -> None:
    """하트비트 로그 태스크 (10초 간격)"""
    global _heartbeat_running, orchestrator
    _heartbeat_running = True

    while _heartbeat_running:
        uptime_seconds = int(time.time() - _service_start_time)
        current_state = "UNKNOWN"
        if orchestrator and hasattr(orchestrator, 'state_machine'):
            current_state = orchestrator.state_machine.current_state.name

        await _logger.info(
            "heartbeat",
            f"Orchestrator Service alive (uptime: {uptime_seconds}s, state: {current_state})",
            metadata={
                "service": "orchestrator",
                "uptime_seconds": uptime_seconds,
                "current_state": current_state,
                "is_running": orchestrator._is_running if orchestrator else False
            }
        )
        await asyncio.sleep(HEARTBEAT_INTERVAL)  # 10초
```

**시작 위치**: `services/orchestrator/app/main.py:134`
```python
asyncio.create_task(heartbeat_task())
```

---

#### ✅ Orchestrator - LLM 프록시 하트비트

**파일**: `services/orchestrator/app/main.py:64-100`

```python
async def llm_heartbeat_task() -> None:
    """
    Phase 27.8: LLM 프록시 하트비트 태스크 (10초 간격)

    vLLM 서비스는 공식 Docker 이미지를 사용하므로 코드 수정이 불가능합니다.
    따라서 Orchestrator에서 vLLM health check를 수행하고 로그를 전송합니다.
    """
    global _heartbeat_running, _llm_logger

    _llm_logger = PipelineLogger("llm")
    vllm_url = os.getenv("LLM_SERVICE_URL", "http://llm:8003")

    while _heartbeat_running:
        try:
            # vLLM health check
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{vllm_url}/health")
                is_healthy = response.status_code == 200

            uptime_seconds = int(time.time() - _service_start_time)
            await _llm_logger.info(
                "heartbeat",
                f"LLM Service monitoring (uptime: {uptime_seconds}s, healthy: {is_healthy})",
                metadata={
                    "service": "llm",  # ← "llm"으로 보고
                    "vllm_healthy": is_healthy,
                    "proxy_uptime_seconds": uptime_seconds
                }
            )
        except Exception as e:
            await _llm_logger.error(
                "heartbeat",
                f"LLM health check failed: {str(e)}",
                metadata={"service": "llm", "error": str(e)}
            )
        await asyncio.sleep(HEARTBEAT_INTERVAL)  # 10초
```

**시작 위치**: `services/orchestrator/app/main.py:137`
```python
asyncio.create_task(llm_heartbeat_task())
```

---

#### ✅ Audio Gateway Service

**파일**: `services/audio_gateway/app/main.py:50-74`

```python
async def heartbeat_task() -> None:
    """하트비트 로그 태스크 (10초 간격)"""
    global _heartbeat_running
    _heartbeat_running = True

    while _heartbeat_running:
        uptime_seconds = int(time.time() - _service_start_time)
        await _logger.info(
            "heartbeat",
            f"Audio Gateway Service alive (uptime: {uptime_seconds}s)",
            metadata={
                "service": "audio_gateway",
                "uptime_seconds": uptime_seconds,
                "redis_connected": redis_client is not None,
                "vad_speaking": vad.is_currently_speaking if vad else False,
                "playback_state": barge_in_detector.playback_state.name if barge_in_detector else "unknown"
            }
        )
        await asyncio.sleep(HEARTBEAT_INTERVAL)  # 10초
```

**시작 위치**: `services/audio_gateway/app/main.py:128`
```python
asyncio.create_task(heartbeat_task())
```

---

#### ✅ Wake Word Service

**파일**: `services/wake_word/app/main.py:84-102`

```python
async def heartbeat_task(self) -> None:
    """하트비트 로그 태스크 (10초 간격)"""
    start_time = time.time()
    while self._running:
        uptime_seconds = int(time.time() - start_time)
        await self._logger.info(
            "heartbeat",
            f"Wake Word Service alive (uptime: {uptime_seconds}s)",
            metadata={
                "service": "wake_word",
                "uptime_seconds": uptime_seconds,
                "redis_connected": self.redis_client is not None
            }
        )
        await asyncio.sleep(10)  # 10초
```

**시작 위치**: `services/wake_word/app/main.py:183`
```python
asyncio.create_task(service.heartbeat_task())
```

---

#### ❌ RAG Service

**파일**: `services/rag/app/main.py`

**현재 상태**: **PipelineLogger 미구현, 하트비트 없음**

- `/health`, `/info` 엔드포인트만 존재
- Redis 연결 없음
- 파이프라인 로깅 완전 누락

---

#### ❌ Embedding Service

**파일**: `services/embedding/app/main.py`

**현재 상태**: **PipelineLogger 미구현, 하트비트 없음**

- `/health`, `/info` 엔드포인트만 존재
- Redis 연결 없음
- 파이프라인 로깅 완전 누락

---

### 3.3 서비스별 구현 요약표

| 서비스 | 파일 위치 | PipelineLogger | 하트비트 | Redis 발행 | 상태 |
|--------|----------|---------------|---------|-----------|------|
| **STT** | `services/stt/app/main.py:44` | ✅ | ✅ 10초 | ✅ `edgevoice:logs:pipeline` | **구현됨** |
| **TTS** | `services/tts/app/main.py:33` | ✅ | ✅ 10초 | ✅ `edgevoice:logs:pipeline` | **구현됨** |
| **Orchestrator** | `services/orchestrator/app/main.py:36` | ✅ | ✅ 10초 | ✅ `edgevoice:logs:pipeline` | **구현됨** |
| **LLM (프록시)** | `services/orchestrator/app/main.py:64` | ✅ | ✅ 10초 | ✅ `edgevoice:logs:pipeline` | **프록시** |
| **Audio Gateway** | `services/audio_gateway/app/main.py:50` | ✅ | ✅ 10초 | ✅ `edgevoice:logs:pipeline` | **구현됨** |
| **Wake Word** | `services/wake_word/app/main.py:84` | ✅ | ✅ 10초 | ✅ `edgevoice:logs:pipeline` | **구현됨** |
| **RAG** | `services/rag/app/main.py` | ❌ | ❌ | ❌ | **미구현** |
| **Embedding** | `services/embedding/app/main.py` | ❌ | ❌ | ❌ | **미구현** |

### 3.4 현재 문제점 진단

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       현재 로깅 플로우 문제점                                 │
└─────────────────────────────────────────────────────────────────────────────┘

┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐
│    STT    │  │    TTS    │  │Orchestrator│  │Wake Word │  │Audio GW   │
│ ✅ 로그발행 │  │ ✅ 로그발행 │  │ ✅ 로그발행 │  │ ✅ 로그발행 │  │ ✅ 로그발행 │
└─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘
      │              │              │              │              │
      └──────────────┴──────────────┴──────────────┴──────────────┘
                                    │
                                    ▼
      ┌──────────────────────────────┐
      │   edgevoice:logs:pipeline    │ ← 서비스들이 발행하는 채널 ✅
      └──────────────┬───────────────┘
                     │
                     ▼
      ┌──────────────────────────────┐
      │   LogSubscriber              │ ← 이 채널 구독 ✅
      │   (subscribe: logs:pipeline) │
      └──────────────┬───────────────┘
                     │
                     │ ⚠️ DB 저장 로직 불완전
                     │
                     ▼
      ┌──────────────────────────────┐
      │   LogBroadcaster             │
      │   (publish: edgevoice:logs)  │ ← 다른 채널로 발행 ❌
      └──────────────┬───────────────┘
                     │
                     ▼
      ┌──────────────────────────────┐
      │   Dashboard SSE Stream       │
      │   (subscribe: edgevoice:logs)│ ← 이 채널에 데이터 없음 ❌
      └──────────────────────────────┘
```

**문제 요약**:
1. ✅ **서비스 → Redis 발행**: 6개 서비스가 정상적으로 `edgevoice:logs:pipeline` 채널로 발행
2. ✅ **Redis 채널 통일**: LogBroadcaster도 동일 채널 사용 (해결됨)
3. ❌ **LogSubscriber → DB**: 수신은 하지만 **DB 저장 로직 없음**
4. ❌ **RAG, Embedding**: 로깅 미구현

---

## 4. 핵심 원인 분석

### 4.1 원인 관계도

```
┌─────────────────────────────────────────────────────────────────┐
│                     ROOT CAUSE ANALYSIS                          │
└─────────────────────────────────────────────────────────────────┘

                    ┌─────────────────────┐
                    │ LogSubscriber       │
                    │ DB 저장 로직 없음    │  ← 핵심 원인
                    └────────┬────────────┘
                             │
                             ▼
                    ┌─────────────────────┐
                    │ pipeline_logs 테이블 │
                    │    데이터 없음       │
                    └─────────┬───────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │ Dashboard Pipeline  │
                    │ Logs 빈 목록 표시   │
                    └─────────────────────┘
```

### 4.2 문제 영향 체인

1. ~~**Redis 채널 불일치**~~ → ✅ **해결됨**
2. **LogSubscriber-DB 미연결** → 수신해도 저장 안됨 (핵심 문제)
3. **pipeline_logs 비어있음** → Dashboard Pipeline Logs 빈 목록 표시

### 4.3 Dashboard 로그 표시 아키텍처

#### Frontend (Dashboard)

**파일**: `services/backend/static/index.html`

```html
<!-- Line 825-828: 로그 컨테이너 -->
<div id="logsContainer">
    <div id="logsList"></div>  <!-- 로그 항목들이 여기에 추가됨 -->
</div>
```

**JavaScript 함수들**:

| 함수 | 위치 (라인) | 역할 |
|------|------------|------|
| `fetchLogs()` | 1812-1840 | `/api/logs`에서 DB 로그 조회 → `#logsList`에 표시 |
| `startLiveLogStream()` | 1842-1880 | `/api/logs/stream` SSE 구독 → 실시간 로그 추가 |
| `addLogEntry(log)` | 1787-1810 | 개별 로그를 `#logsList`에 DOM 추가 |
| `createLogEntry(log)` | 1770-1785 | 로그 DOM 요소 생성 |

**데이터 흐름**:
```
1. 초기 로드: fetchLogs() → GET /api/logs → DB 조회 → #logsList 표시
2. 실시간:   startLiveLogStream() → EventSource(/api/logs/stream) → SSE 수신 → addLogEntry()
```

#### Backend API

**파일**: `services/backend/app/routes/logs.py`

| 엔드포인트 | 함수 | 라인 | 데이터 소스 |
|-----------|------|------|------------|
| `GET /api/logs` | `list_logs()` | 141-167 | `PipelineLogRepository.list_recent()` → **DB** |
| `GET /api/logs/stream` | `stream_logs()` | 170-195 | `create_log_event_generator()` → **Redis Pub/Sub** |

**SSE Generator** (`create_log_event_generator()`, Line 35-109):
```python
# Line 60: Redis 채널 구독
await pubsub.subscribe(LOGS_CHANNEL)  # LOGS_CHANNEL = "edgevoice:logs:pipeline"

# Line 72-91: 메시지 수신 및 SSE 전송
async for message in pubsub.listen():
    if parsed.get("type") == "log":
        log_data = parsed.get("data", {})
        yield f"event: log\ndata: {json.dumps(log_data)}\n\n"
```

#### 현재 문제 진단

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                      Dashboard 로그 표시 데이터 흐름                              │
└────────────────────────────────────────────────────────────────────────────────┘

[서비스 하트비트] ───────────────────────────────────────────────────────────────┐
      │                                                                          │
      │ PipelineLogger.info()                                                    │
      ▼                                                                          │
┌─────────────────────────────────────┐                                          │
│ Redis: "edgevoice:logs:pipeline"    │ ← 서비스들이 발행 ✅                       │
└───────────────┬─────────────────────┘                                          │
                │                                                                │
        ┌───────┴───────┐                                                        │
        │               │                                                        │
        ▼               ▼                                                        │
┌───────────────┐  ┌────────────────────────────────────────────────┐            │
│ LogSubscriber │  │ logs.py SSE Generator                          │            │
│ ✅ 구독 중     │  │ (subscribe: edgevoice:logs:pipeline) ✅         │            │
│               │  │                                                │            │
│ ⚠️ DB 저장    │  │ Line 60: await pubsub.subscribe(LOGS_CHANNEL)  │            │
│    로직 없음   │  │ Line 72-91: async for message → yield SSE      │            │
└───────┬───────┘  └────────────────────┬───────────────────────────┘            │
        │                               │                                        │
        │ (콜백만 호출)                  │ SSE: event: log                        │
        ▼                               ▼                                        │
┌───────────────┐              ┌────────────────────────────────────┐            │
│ DB 저장 안됨   │              │ Dashboard Frontend                 │            │
│ ❌            │              │                                    │            │
└───────────────┘              │ startLiveLogStream() → EventSource │            │
                               │ Line 1857-1860:                    │            │
                               │   const log = JSON.parse(data)     │            │
                               │   addLogEntry(log)                 │ ← 실시간 ✅ │
                               └────────────────────────────────────┘            │
                                                                                 │
┌────────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│  [초기 로드 시]                                                                 │
│                                                                                │
│  fetchLogs() → GET /api/logs                                                   │
│        ↓                                                                       │
│  PipelineLogRepository.list_recent() → SELECT * FROM pipeline_logs             │
│        ↓                                                                       │
│  ❌ DB 비어있음 (LogSubscriber가 저장 안함)                                       │
│        ↓                                                                       │
│  Dashboard: 빈 목록 표시                                                        │
└────────────────────────────────────────────────────────────────────────────────┘
```

**핵심 발견**:
1. **실시간 SSE 스트리밍은 작동 가능** - `logs.py`의 SSE Generator가 동일 채널 구독 ✅
2. **초기 로드(DB 조회)는 빈 목록** - `LogSubscriber`가 DB 저장 안함 ❌
3. **문제의 핵심**: `LogSubscriber.listen()`에 `PipelineLogRepository.create()` 호출이 없음

---

## 5. 수정 권장사항

### ~~5.1 Redis 채널 통일~~ ✅ **완료**

**파일: `services/backend/app/services/log_broadcaster.py`** - **수정 완료**

```python
# Phase 31.2: 채널 통합 (edgevoice:logs -> edgevoice:logs:pipeline)
from ..constants.redis_channels import RedisChannels

# Redis 로그 채널 (log_subscriber.py와 동일)
LOGS_CHANNEL = RedisChannels.PIPELINE_LOGS  # "edgevoice:logs:pipeline" ✅
```

### 5.2 LogSubscriber DB 연결 (우선순위: CRITICAL)

**파일: `services/backend/app/services/log_subscriber.py`**

```python
# listen() 메서드 수정
async def listen(self, on_log: Optional[Callable] = None):
    repo = PipelineLogRepository()

    async for message in pubsub.listen():
        log_data = json.loads(message["data"])

        # DB에 저장
        await repo.create(
            service=log_data.get("service", "unknown"),
            stage=log_data.get("stage", "general"),
            message=log_data.get("message", ""),
            level=log_data.get("level", "INFO"),
            session_id=log_data.get("session_id"),
            duration_ms=log_data.get("duration_ms"),
            metadata=log_data.get("metadata")
        )

        if on_log:
            await on_log(log_data)
```

### 5.3 pipeline_logs 테이블 관리 (우선순위: MEDIUM)

```sql
-- 자동 정리 정책 추가 (30일 이상 로그 삭제)
CREATE OR REPLACE FUNCTION cleanup_old_pipeline_logs()
RETURNS void AS $$
BEGIN
    DELETE FROM pipeline_logs
    WHERE created_at < NOW() - INTERVAL '30 days';
END;
$$ LANGUAGE plpgsql;

-- 매일 정리 실행 (pg_cron 또는 애플리케이션 레벨)
```

### 5.4 RAG/Embedding 서비스 로깅 추가 (우선순위: MEDIUM)

**RAG Service** (`services/rag/app/main.py`):
```python
# 추가 필요
from shared.pipeline_logger import PipelineLogger
import asyncio
import time

_logger = PipelineLogger("rag")
_heartbeat_running = False
_start_time = 0

async def heartbeat_task():
    global _heartbeat_running
    _heartbeat_running = True
    while _heartbeat_running:
        uptime = int(time.time() - _start_time)
        await _logger.info(
            "heartbeat",
            f"RAG Service alive (uptime: {uptime}s)",
            metadata={"service": "rag", "uptime_seconds": uptime}
        )
        await asyncio.sleep(10)

# lifespan에 추가:
# asyncio.create_task(heartbeat_task())
```

**Embedding Service** (`services/embedding/app/main.py`):
```python
# 동일한 패턴으로 추가
_logger = PipelineLogger("embedding")
# ... heartbeat_task 추가
```

---

## 6. 파일 위치 참조

### 6.1 핵심 파일 목록

| 분류 | 파일 경로 | 수정 필요 | 상태 |
|------|----------|----------|------|
| Redis 채널 상수 | `services/backend/app/constants/redis_channels.py` | - | ✅ |
| 로그 브로드캐스터 | `services/backend/app/services/log_broadcaster.py:15` | ~~YES~~ | ✅ **완료** |
| 로그 구독자 | `services/backend/app/services/log_subscriber.py:19` | ~~YES~~ | ✅ **완료** (Phase 31.3) |
| 로그 저장소 | `services/backend/app/repositories/pipeline_log_repository.py` | - | ✅ |
| DB 스키마 | `config/postgres/init.sql:246-275` | - | ✅ |

### 6.2 서비스별 하트비트 코드 위치

| 서비스 | 파일 | 라인 | 함수명 |
|--------|------|------|--------|
| STT | `services/stt/app/main.py` | 44-67 | `heartbeat_task()` |
| TTS | `services/tts/app/main.py` | 33-46 | `heartbeat_loop()` |
| Orchestrator | `services/orchestrator/app/main.py` | 36-62 | `heartbeat_task()` |
| LLM (프록시) | `services/orchestrator/app/main.py` | 64-100 | `llm_heartbeat_task()` |
| Audio Gateway | `services/audio_gateway/app/main.py` | 50-74 | `heartbeat_task()` |
| Wake Word | `services/wake_word/app/main.py` | 84-102 | `heartbeat_task()` |
| RAG | - | - | **미구현** |
| Embedding | - | - | **미구현** |

### 6.3 Redis 채널 현황

| 용도 | 설계된 채널명 | 실제 사용 채널 | 상태 |
|------|-------------|---------------|------|
| 파이프라인 로그 | `edgevoice:logs:pipeline` | `edgevoice:logs:pipeline` | ✅ **통일됨** |
| 시스템 상태 | `edgevoice:system:status` | 정상 | ✅ |
| STT 결과 | `edgevoice:stt:result` | 정상 | ✅ |
| TTS 결과 | `edgevoice:tts:result` | 정상 | ✅ |

---

## 7. Redis 채널 상수 상세 분석

### 7.1 채널 상수 정의 파일별 분석

#### 📁 파일 1: `shared/pipeline_logger/logger.py:20`

```python
DEFAULT_CHANNEL = "edgevoice:logs:pipeline"
```

| 항목 | 내용 |
|------|------|
| **위치** | `shared/pipeline_logger/` (공유 모듈) |
| **클래스** | `PipelineLogger` |
| **상수값** | `"edgevoice:logs:pipeline"` |
| **역할** | 모든 마이크로서비스에서 로그를 발행할 때 사용하는 **기본 채널** |
| **사용처** | STT, TTS, Orchestrator, Audio Gateway, Wake Word 서비스의 heartbeat 및 파이프라인 로그 |
| **동작** | `log()` 메소드 호출 시 `redis.publish(self.channel, ...)` 실행 (line 69) |

**핵심 코드**:
```python
class PipelineLogger:
    DEFAULT_CHANNEL = "edgevoice:logs:pipeline"

    def __init__(self, service_name: str, redis_client=None, channel: str = None):
        self.channel = channel or self.DEFAULT_CHANNEL  # line 38

    async def log(self, event: str, ...):
        if self.redis:
            await self.redis.publish(self.channel, json.dumps(log_entry))  # line 69
```

**데이터 흐름**:
```
[서비스] → PipelineLogger.info() → redis.publish("edgevoice:logs:pipeline", log_entry)
```

---

#### 📁 파일 2: `services/backend/app/constants/redis_channels.py:16`

```python
PIPELINE_LOGS = "edgevoice:logs:pipeline"
```

| 항목 | 내용 |
|------|------|
| **위치** | `services/backend/app/constants/` (Backend 서비스) |
| **클래스** | `RedisChannels` |
| **상수값** | `"edgevoice:logs:pipeline"` |
| **역할** | Backend 서비스 내부에서 사용하는 **중앙 집중식 채널 상수 정의** |
| **사용처** | `log_subscriber.py`에서 import하여 사용 |
| **동작** | 상수 정의만 담당 (실제 Redis 연결 없음) |

**핵심 코드**:
```python
class RedisChannels:
    """Redis Pub/Sub 채널 상수"""

    # Orchestrator 상태 브로드캐스트 채널
    ORCHESTRATOR_STATE = "edgevoice:orchestrator:state"

    # 파이프라인 로그 채널
    PIPELINE_LOGS = "edgevoice:logs:pipeline"

    # 설정 브로드캐스트 채널
    SETTINGS_BROADCAST = "edgevoice:settings:broadcast"

    # 대시보드 업데이트 채널
    DASHBOARD_UPDATES = "dashboard:updates"

    # 설정 타입별 채널
    SETTINGS_TTS = "settings:tts"
    SETTINGS_STT = "settings:stt"
    SETTINGS_LLM = "settings:llm"
    SETTINGS_AUDIO = "settings:audio"
```

**설계 목적**:
- 채널명을 한 곳에서 관리하여 일관성 유지
- 모든 Redis 채널의 Single Source of Truth

---

#### 📁 파일 3: `services/backend/app/services/log_broadcaster.py:15` ✅ **수정 완료**

```python
LOGS_CHANNEL = RedisChannels.PIPELINE_LOGS  # "edgevoice:logs:pipeline"
```

| 항목 | 내용 |
|------|------|
| **위치** | `services/backend/app/services/` (Backend 서비스) |
| **클래스** | `LogBroadcaster` |
| **상수값** | `RedisChannels.PIPELINE_LOGS` = `"edgevoice:logs:pipeline"` ✅ |
| **역할** | Backend API에서 생성된 로그를 SSE 클라이언트로 브로드캐스트 |
| **사용처** | `logs.py` 라우터의 `create_log()` 엔드포인트에서 호출 |
| **동작** | `broadcast()` 메소드에서 `redis.publish(LOGS_CHANNEL, ...)` 실행 (line 64) |

**현재 코드** (수정됨):
```python
# Phase 31.2: 채널 통합 (edgevoice:logs -> edgevoice:logs:pipeline)
from ..constants.redis_channels import RedisChannels

# Redis 로그 채널 (log_subscriber.py와 동일)
LOGS_CHANNEL = RedisChannels.PIPELINE_LOGS  # "edgevoice:logs:pipeline" ✅

class LogBroadcaster:
    async def broadcast(self, log_data: Dict[str, Any]) -> bool:
        message = {"type": "log", "data": log_data}
        await redis_client.publish(LOGS_CHANNEL, json.dumps(message))  # line 64
```

**상태**: ✅ **채널 통일 완료** - Subscriber와 동일한 채널 사용

---

#### 📁 파일 4: `services/backend/app/services/log_subscriber.py:19`

```python
LOGS_CHANNEL = RedisChannels.PIPELINE_LOGS  # "edgevoice:logs:pipeline"
```

| 항목 | 내용 |
|------|------|
| **위치** | `services/backend/app/services/` (Backend 서비스) |
| **클래스** | `LogSubscriber` |
| **상수값** | `RedisChannels.PIPELINE_LOGS` = `"edgevoice:logs:pipeline"` ✅ |
| **역할** | 서비스들이 발행한 로그를 구독하여 처리 |
| **사용처** | Backend 앱 시작 시 백그라운드 태스크로 실행 |
| **동작** | `subscribe()` 메소드에서 `pubsub.subscribe(LOGS_CHANNEL)` 실행 (line 63) |

**핵심 코드**:
```python
# Line 17-19 - 올바르게 중앙 상수 사용
from ..constants.redis_channels import RedisChannels

LOGS_CHANNEL = RedisChannels.PIPELINE_LOGS  # "edgevoice:logs:pipeline"

class LogSubscriber:
    async def subscribe(self) -> None:
        await self._pubsub.subscribe(LOGS_CHANNEL)  # line 63

    async def listen(self):
        async for message in self._pubsub.listen():  # line 77
            # 메시지 처리 (DB 저장 로직 없음 - 문제점)
            if self._on_log:
                await self._on_log(log_data)
```

**현재 문제**:
- 채널은 올바르게 구독하지만
- `listen()` 메소드가 **DB 저장 로직이 없음** (콜백만 호출)

---

### 7.2 채널 상수 비교표

| 파일 | 상수명 | 값 | 용도 | 상태 |
|------|--------|-----|------|------|
| `shared/pipeline_logger/logger.py:20` | `DEFAULT_CHANNEL` | `edgevoice:logs:pipeline` | 서비스 → Redis 발행 | ✅ 정상 |
| `backend/constants/redis_channels.py:16` | `PIPELINE_LOGS` | `edgevoice:logs:pipeline` | 중앙 상수 정의 | ✅ 정상 |
| `backend/services/log_subscriber.py:19` | `LOGS_CHANNEL` | `RedisChannels.PIPELINE_LOGS` | Redis → Backend 구독 | ✅ 정상 |
| `backend/services/log_broadcaster.py:15` | `LOGS_CHANNEL` | `edgevoice:logs` | Backend → SSE 발행 | ❌ **불일치** |

---

### 7.3 서비스별 채널 사용 현황

#### 발행(Publish) 측

| 서비스 | 클래스/모듈 | 메소드 | 채널 | 파일:라인 |
|--------|-------------|--------|------|-----------|
| **STT** | `PipelineLogger` | `info()`, `log()` | `edgevoice:logs:pipeline` | `stt/app/main.py:44-67` |
| **TTS** | `PipelineLogger` | `info()`, `log()` | `edgevoice:logs:pipeline` | `tts/app/main.py:33-46` |
| **Orchestrator** | `PipelineLogger` | `info()`, `log()` | `edgevoice:logs:pipeline` | `orchestrator/app/main.py:36-62` |
| **LLM (프록시)** | `PipelineLogger` | `info()`, `error()` | `edgevoice:logs:pipeline` | `orchestrator/app/main.py:64-100` |
| **Audio Gateway** | `PipelineLogger` | `info()`, `log()` | `edgevoice:logs:pipeline` | `audio_gateway/app/main.py:50-74` |
| **Wake Word** | `PipelineLogger` | `info()`, `log()` | `edgevoice:logs:pipeline` | `wake_word/app/main.py:84-102` |
| **RAG** | - | - | - | ❌ 미구현 |
| **Embedding** | - | - | - | ❌ 미구현 |

#### 구독(Subscribe) 측

| 서비스 | 클래스 | 메소드 | 구독 채널 | 파일:라인 | 상태 |
|--------|--------|--------|-----------|-----------|------|
| **Backend** | `LogSubscriber` | `subscribe()` | `edgevoice:logs:pipeline` | `log_subscriber.py:63` | ✅ 올바름 |
| **Backend** | `LogSubscriber` | `listen()` | `edgevoice:logs:pipeline` | `log_subscriber.py:77` | ✅ 올바름 |
| **Backend** | `create_log_event_generator()` | (SSE용) | `edgevoice:logs` | `logs.py:60` | ❌ **불일치** |

#### 브로드캐스트(Broadcast) 측

| 서비스 | 클래스 | 메소드 | 발행 채널 | 파일:라인 | 상태 |
|--------|--------|--------|-----------|-----------|------|
| **Backend** | `LogBroadcaster` | `broadcast()` | `edgevoice:logs` | `log_broadcaster.py:63` | ❌ **불일치** |
| **Backend** | `broadcast_log()` | (편의 함수) | `edgevoice:logs` | `log_broadcaster.py:100` | ❌ **불일치** |

---

### 7.4 데이터 흐름 다이어그램

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                              현재 데이터 흐름                                    │
└────────────────────────────────────────────────────────────────────────────────┘

 [STT/TTS/Orchestrator/Audio GW/Wake Word]
        │
        │ PipelineLogger.info()
        │ channel = DEFAULT_CHANNEL
        ▼
┌─────────────────────────────────┐
│ Redis: "edgevoice:logs:pipeline"│  ← 서비스들이 발행하는 채널 ✅
└───────────────┬─────────────────┘
                │
        ┌───────┴───────┐
        │               │
        ▼               ▼
┌───────────────┐  ┌────────────────────┐
│ LogSubscriber │  │ (아무도 구독 안함)  │
│ ✅ 올바른 채널 │  │                    │
│ 구독 중       │  │                    │
└───────┬───────┘  └────────────────────┘
        │
        │ listen() → 콜백 호출
        │ ⚠️ DB 저장 로직 없음
        ▼
┌─────────────────────────────────┐
│ LogBroadcaster.broadcast()      │
│ channel = "edgevoice:logs" ❌   │  ← 다른 채널로 발행
└───────────────┬─────────────────┘
                │
                ▼
┌─────────────────────────────────┐
│ Redis: "edgevoice:logs"         │  ← LogBroadcaster가 발행
└───────────────┬─────────────────┘
                │
                ▼
┌─────────────────────────────────┐
│ logs.py SSE Generator           │
│ subscribe("edgevoice:logs")     │  ← 이 채널 구독
│ ⚠️ 서비스 로그는 수신 불가       │
└─────────────────────────────────┘
```

---

### 7.5 채널 불일치 문제 요약

| # | 문제 | 원인 파일 | 현재 값 | 올바른 값 |
|---|------|----------|---------|----------|
| 1 | LogBroadcaster 채널 하드코딩 | `log_broadcaster.py:15` | `"edgevoice:logs"` | `RedisChannels.PIPELINE_LOGS` |
| 2 | SSE Generator 채널 불일치 | `logs.py:60` | `"edgevoice:logs"` (import) | `RedisChannels.PIPELINE_LOGS` |
| 3 | RAG 서비스 PipelineLogger 없음 | `services/rag/` | - | 구현 필요 |
| 4 | Embedding 서비스 PipelineLogger 없음 | `services/embedding/` | - | 구현 필요 |

---

### 7.6 수정 방안

#### 수정 1: `log_broadcaster.py` 채널 통일

```python
# Before (Line 15)
LOGS_CHANNEL = "edgevoice:logs"

# After
from ..constants.redis_channels import RedisChannels
LOGS_CHANNEL = RedisChannels.PIPELINE_LOGS  # "edgevoice:logs:pipeline"
```

#### 수정 2: `logs.py` import 경로 변경

```python
# Before (Line 23)
from ..services.log_broadcaster import broadcast_log, LOGS_CHANNEL

# After - log_subscriber에서 채널 가져오기 (또는 직접 RedisChannels 사용)
from ..constants.redis_channels import RedisChannels
LOGS_CHANNEL = RedisChannels.PIPELINE_LOGS
```

---

## 결론

### 현재 구현 상태 요약

| 구분 | 상태 | 비고 |
|------|------|------|
| 서비스 하트비트 발행 | ✅ 6/8 구현 | STT, TTS, Orchestrator, LLM(프록시), Audio GW, Wake Word |
| Redis 채널 발행 | ✅ 정상 | `edgevoice:logs:pipeline` 채널 사용 |
| LogSubscriber 구독 | ✅ 정상 | 동일 채널 구독 |
| LogBroadcaster 채널 | ✅ **해결됨** | `RedisChannels.PIPELINE_LOGS` 사용 |
| SSE 실시간 스트리밍 | ✅ 작동 가능 | `logs.py`의 SSE Generator가 동일 채널 구독 |
| LogSubscriber → DB 저장 | ✅ **해결됨** | Phase 31.3에서 `_save_log_to_db()` 구현 |
| RAG/Embedding 로깅 | ❌ 미구현 | 하트비트 코드 추가 필요 (MEDIUM) |

### 해결된 문제
- ~~**Redis 채널 통일**~~: `log_broadcaster.py`에서 채널명을 `RedisChannels.PIPELINE_LOGS`로 변경 ✅
- ~~**LogSubscriber DB 저장**~~: `log_subscriber.py`에 `_save_log_to_db()` 메서드 추가 (Phase 31.3) ✅

### ~~즉시 수정 필요 (CRITICAL)~~ ✅ **해결됨**
1. ~~**LogSubscriber DB 연결**: 수신된 로그를 `PipelineLogRepository.create()`로 저장~~ → **Phase 31.3에서 구현 완료**

### 권장 수정 (MEDIUM)
2. **RAG/Embedding 하트비트 추가**: 2개 서비스에 `heartbeat_task()` 구현

### 선택적 개선 (MEDIUM)
3. **pipeline_logs 자동 정리**: 오래된 로그 자동 삭제 정책 구현

---

*이 보고서는 EdgeVoice 시스템의 파이프라인 로깅 문제를 분석한 결과입니다.*
*최종 업데이트: 2025-12-12*
