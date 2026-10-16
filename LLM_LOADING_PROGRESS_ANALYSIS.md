# LLM Loading Progress 분석 보고서

## 1. 개요

LLM 모델 로딩 시 진행률(%)이 Pipeline Logs와 Dashboard에 표시되지 않는 문제를 분석한 보고서입니다.

## 2. 현재 아키텍처

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   vLLM (LLM)    │────>│     Backend     │────>│    Frontend     │
│  Docker 컨테이너 │     │  Dashboard API  │     │   Dashboard     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
       │                        │
       │ Docker logs            │ SSE
       └───────────────────────>│
                               \/
                        Redis Pub/Sub (미사용)
```

## 3. 발견된 문제점

### 3.1 vLLM 로그 패턴 불일치

**예상 패턴 (코드에 정의됨):**
```python
# services/backend/app/routes/dashboard.py:255
weight_pattern = r"Loading model weights:\s*(\d+)%"
```

**실제 vLLM 로그 패턴:**
```
Loading safetensors checkpoint shards:  33% Completed | 1/3 [01:07<02:15, 67.93s/it]
Loading safetensors checkpoint shards:  67% Completed | 2/3 [02:15<01:07, 67.99s/it]
Loading safetensors checkpoint shards: 100% Completed | 3/3 [02:50<00:00, 52.67s/it]
```

**결과:** 파싱 함수 `_parse_vllm_progress()`가 실제 로그를 인식하지 못하여 항상 `None` 반환

### 3.2 LLM 진행률이 Pipeline Logs에 기록되지 않음

**원인 분석:**

| 구성요소 | 파일 | 상태 |
|---------|------|------|
| `log_llm_loading_progress()` | `orchestrator/app/llm_progress.py:145` | **정의됨** |
| 함수 호출 위치 | - | **없음** |

`log_llm_loading_progress()` 함수가 정의되어 있지만, 실제로 호출하는 코드가 없습니다.

### 3.3 Dashboard SSE에서 진행률 데이터 누락

**Dashboard SSE 이벤트 흐름:**
```python
# services/backend/app/routes/dashboard.py:599-617
# 5초마다 LLM 상태 체크
if update_count % 5 == 0:
    llm_info = await construct_llm_info()
    # service_status 이벤트에 progress_percent, loading_stage 포함
    service_data = {
        "service": "llm",
        "status": llm_status,
        "docker_health": llm_info.get("docker_health"),
        "model": llm_info.get("model"),
        # progress_percent, loading_stage 등 누락됨!
    }
```

**문제:** `construct_llm_info()`가 반환하는 `progress_percent`, `loading_stage`, `loading_message` 필드가 SSE `service_status` 이벤트에 포함되지 않음

### 3.4 Docker Health Status 의존성

진행률 표시 조건:
```python
# services/backend/app/routes/dashboard.py:422-423
if status == "loading":
    progress_info = await get_llm_loading_progress("ev-llm")
```

`status == "loading"`이 되려면:
```python
# services/backend/app/routes/dashboard.py:398-399
elif docker_health == "starting":
    status = "loading"
```

**문제:** vLLM 컨테이너에 Docker HEALTHCHECK가 설정되어 있지 않으면 `docker_health`가 `"none"`이 되어 `status`가 `"loading"`이 아닌 `"offline"`이 됨

## 4. 근본 원인 요약

| # | 원인 | 영향 |
|---|------|------|
| 1 | vLLM 로그 패턴 불일치 | Docker logs에서 진행률 파싱 실패 |
| 2 | `log_llm_loading_progress()` 미호출 | Pipeline Logs에 진행률 기록 안됨 |
| 3 | SSE 이벤트에 progress 필드 누락 | Frontend에 진행률 전달 안됨 |
| 4 | Docker HEALTHCHECK 미설정 가능성 | loading 상태 감지 실패 |

## 5. 현재 코드 흐름 분석

### 5.1 Dashboard Init (페이지 로드 시)
```
Frontend → GET /api/dashboard/init
         → construct_llm_info()
         → get_container_health_status("ev-llm")
         → docker_health가 "starting"인 경우만 progress 정보 추가
         → Frontend에 전달
```

### 5.2 Dashboard SSE Stream
```
Frontend ← SSE /api/dashboard/stream
         ← 5초마다 service_status 이벤트
         ← progress_percent, loading_stage 필드 누락됨
```

### 5.3 Pipeline Logs SSE
```
Services → Redis PUBLISH "edgevoice:logs:pipeline"
         → Backend SSE /api/logs/stream
         → Frontend Logs 탭
         (LLM 로딩 진행률은 Redis에 발행되지 않음)
```

## 6. 권장 수정 사항

### 6.1 vLLM 로그 패턴 수정 (우선순위: 높음) ✅ 구현 완료

```python
# services/backend/app/routes/dashboard.py
def _parse_vllm_progress(log_text: str) -> Optional[Dict[str, Any]]:
    # 패턴 추가: safetensors checkpoint shards
    safetensors_pattern = r"Loading safetensors checkpoint shards:\s*(\d+)%"
    match = re.search(safetensors_pattern, log_text)
    if match:
        percent = int(match.group(1))
        return {
            "progress_percent": percent,
            "stage": "loading_weights",
            "message": f"Loading checkpoint shards: {percent}%"
        }
    # 기존 패턴 유지...
```

### 6.2 SSE 이벤트에 progress 필드 추가 (우선순위: 높음) ✅ 구현 완료

```python
# services/backend/app/routes/dashboard.py:608-615
service_data = {
    "service": "llm",
    "status": llm_status,
    "docker_health": llm_info.get("docker_health"),
    "model": llm_info.get("model"),
    # 추가 필드:
    "progress_percent": llm_info.get("progress_percent"),
    "loading_stage": llm_info.get("loading_stage"),
    "loading_message": llm_info.get("loading_message"),
    "elapsed_seconds": llm_info.get("elapsed_seconds"),
    "timestamp": time.time()
}
```

### 6.3 LLM 진행률 Pipeline Logs 발행 (우선순위: 중간) ✅ 구현 완료

vLLM 컨테이너 시작 시 모니터링 태스크 추가:
```python
# 새 파일 또는 기존 orchestrator에 추가
async def monitor_llm_loading():
    while True:
        progress = await get_llm_loading_progress("ev-llm")
        if progress["stage"] != "unknown":
            await log_llm_loading_progress(
                progress["progress_percent"],
                progress["stage"],
                progress["message"]
            )
        if progress["stage"] == "complete":
            break
        await asyncio.sleep(2)
```

### 6.4 Docker HEALTHCHECK 확인 (우선순위: 중간)

docker-compose.dev.yml에서 LLM 서비스 healthcheck 설정 확인:
```yaml
services:
  llm:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8003/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 300s  # 모델 로딩 시간 고려
```

## 7. 결론

LLM 로딩 진행률이 표시되지 않는 주요 원인:

1. **vLLM 로그 패턴 변경**: vLLM 버전 업데이트로 로그 형식이 변경됨
2. **구현 미완성**: `log_llm_loading_progress()` 함수가 호출되지 않음
3. **SSE 데이터 누락**: Dashboard SSE에서 progress 필드가 전달되지 않음

권장 작업 순서:
1. vLLM 로그 파싱 패턴 수정
2. Dashboard SSE 이벤트에 progress 필드 추가
3. Pipeline Logs에 LLM 진행률 발행 기능 구현

---

## 8. Phase 35: 구현 완료 내역

### 8.1 수정된 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `services/backend/app/routes/dashboard.py` | vLLM 로그 패턴 수정, SSE progress 필드 추가 |
| `services/backend/app/services/llm_loading_monitor.py` | 신규 생성 - LLM 로딩 모니터 서비스 |
| `services/backend/app/main.py` | LLM 모니터 시작/종료 호출 추가 |
| `services/backend/static/index.html` | Frontend LLM 상태 표시 로직 추가 |

### 8.2 dashboard.py - vLLM 로그 패턴 수정

**추가된 패턴:**
```python
def _parse_vllm_progress(log_text: str) -> Optional[Dict[str, Any]]:
    if not log_text:
        return None

    # 패턴 1: 모델 로딩 완료 - Application startup complete
    if "application startup complete" in log_text.lower():
        print(f"[LLM Progress] Pattern matched: startup complete")
        return {
            "progress_percent": 100,
            "stage": "complete",
            "message": "Model loaded successfully"
        }

    # 패턴 2: safetensors checkpoint shards 로딩 (vLLM 0.12+)
    safetensors_pattern = r"Loading safetensors checkpoint shards:\s*(\d+)%"
    match = re.search(safetensors_pattern, log_text)
    if match:
        percent = int(match.group(1))
        print(f"[LLM Progress] Pattern matched: safetensors {percent}%")
        return {
            "progress_percent": percent,
            "stage": "loading_weights",
            "message": f"Loading: {percent}%"
        }

    # 패턴 3: CUDA graphs 캡처 (90-100% 구간)
    cuda_pattern = r"Capturing CUDA graphs.*?:\s*(\d+)%"
    match = re.search(cuda_pattern, log_text)
    if match:
        percent = int(match.group(1))
        adjusted = 90 + int(percent * 0.1)
        print(f"[LLM Progress] Pattern matched: CUDA graphs {adjusted}%")
        return {
            "progress_percent": adjusted,
            "stage": "cuda_graphs",
            "message": f"Optimizing: {adjusted}%"
        }

    # 패턴 4: 초기화 단계
    if "starting to load model" in log_text.lower():
        print(f"[LLM Progress] Pattern matched: starting")
        return {
            "progress_percent": 5,
            "stage": "starting",
            "message": "Starting..."
        }

    if "initializing" in log_text.lower() or "init engine" in log_text.lower():
        print(f"[LLM Progress] Pattern matched: initializing")
        return {
            "progress_percent": 0,
            "stage": "initializing",
            "message": "Starting..."
        }

    return None
```

### 8.3 dashboard.py - SSE 이벤트 progress 필드 추가

```python
# Phase 35: progress 필드 추가
llm_progress = llm_info.get("progress_percent")
llm_stage = llm_info.get("loading_stage")

service_data = {
    "service": "llm",
    "status": llm_status,
    "docker_health": llm_info.get("docker_health"),
    "model": llm_info.get("model"),
    # Phase 35: progress 필드 추가
    "progress_percent": llm_progress,
    "loading_stage": llm_stage,
    "loading_message": llm_info.get("loading_message"),
    "elapsed_seconds": llm_info.get("elapsed_seconds"),
    "latency_ms": llm_info.get("latency_ms"),
    "timestamp": time.time()
}
print(f"[Dashboard SSE] LLM status update: status={llm_status}, progress={llm_progress}%, stage={llm_stage}")
```

### 8.4 llm_loading_monitor.py - 신규 서비스

**기능:**
- vLLM Docker 컨테이너 로그 모니터링
- 진행률 파싱 및 Redis Pipeline Logs 채널에 발행
- LLM health check로 로딩 완료 감지
- 중복 발행 방지 (같은 진행률/단계면 스킵)

**주요 클래스/함수:**
```python
class LLMLoadingMonitor:
    async def connect()           # Redis 연결
    async def close()             # 연결 종료
    async def publish_progress()  # Pipeline Logs에 진행률 발행
    async def get_llm_loading_progress()  # Docker logs에서 진행률 조회
    async def check_llm_health()  # LLM 서비스 health check
    async def monitor()           # 메인 모니터링 루프

async def start_llm_monitor()     # 모니터 시작
async def stop_llm_monitor()      # 모니터 중지
```

### 8.5 main.py - 모니터 통합

```python
from app.services.llm_loading_monitor import start_llm_monitor, stop_llm_monitor

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작 시
    await start_llm_monitor()
    yield
    # 종료 시
    await stop_llm_monitor()
```

### 8.6 index.html - Frontend LLM 상태 표시

**updateServicesGrid() 수정:**
```javascript
// Phase 35: LLM 상태에 따른 서브타이틀 결정
let serviceSubtitle = '';
if (key === 'llm') {
    const progressPercent = service.progress_percent || 0;
    const loadingStage = service.loading_stage || 'unknown';
    const loadingMessage = service.loading_message || '';

    if (isLoading) {
        if (loadingStage === 'initializing' || loadingStage === 'starting') {
            serviceSubtitle = 'Starting...';
        } else if (loadingStage === 'loading_weights' || loadingStage === 'cuda_graphs' || loadingStage === 'estimated') {
            serviceSubtitle = `Loading: ${progressPercent}%`;
        } else {
            serviceSubtitle = loadingMessage || 'Loading...';
        }
    } else if (service.status === 'healthy') {
        serviceSubtitle = `${modelDetail} | Latency: ${latency}`;
    } else {
        serviceSubtitle = 'Offline';
    }
}
```

**updateServiceCard() 수정:**
```javascript
// Phase 35: LLM 진행률 업데이트
if (data.service === 'llm') {
    const progressPercent = data.progress_percent || 0;
    const loadingStage = data.loading_stage || 'unknown';
    const loadingMessage = data.loading_message || '';
    const latencyMs = data.latency_ms;

    let subtitle = '';
    if (data.status === 'loading') {
        if (loadingStage === 'initializing' || loadingStage === 'starting') {
            subtitle = 'Starting...';
        } else if (loadingStage === 'loading_weights' || loadingStage === 'cuda_graphs' || loadingStage === 'estimated') {
            subtitle = `Loading: ${progressPercent}%`;
        } else {
            subtitle = loadingMessage || 'Loading...';
        }
    } else if (data.status === 'healthy') {
        const model = data.model || 'Unknown';
        const latency = latencyMs ? `${latencyMs}ms` : 'N/A';
        subtitle = `${model} | Latency: ${latency}`;
    } else {
        subtitle = 'Offline';
    }

    subtitleEl.textContent = subtitle;
}
```

### 8.7 Dashboard LLM 표시 흐름

```
┌─────────────────────────────────────────────────────────────────┐
│                      LLM 로딩 상태 표시                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  상태 1: 초기화 중                                               │
│  ┌─────────────────────────┐                                    │
│  │  LLM                    │                                    │
│  │  Qwen-14B-AWQ          │  ← 모델명 (미리 설정됨)              │
│  │  Starting...            │  ← 서브타이틀                       │
│  └─────────────────────────┘                                    │
│                                                                 │
│  상태 2: 로딩 중 (0-100%)                                        │
│  ┌─────────────────────────┐                                    │
│  │  LLM                    │                                    │
│  │  Qwen-14B-AWQ          │                                    │
│  │  Loading: 67%           │  ← 진행률 표시                      │
│  └─────────────────────────┘                                    │
│                                                                 │
│  상태 3: 로딩 완료                                               │
│  ┌─────────────────────────┐                                    │
│  │  LLM                    │                                    │
│  │  Qwen-14B-AWQ          │                                    │
│  │  Qwen-14B-AWQ | Latency: 88ms │  ← 모델명 | 지연시간          │
│  └─────────────────────────┘                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 8.8 디버그 출력

각 단계에서 print 문으로 디버그 정보 출력:

```
[LLM Progress] Pattern matched: safetensors 33%
[LLM Progress] Pattern matched: safetensors 67%
[LLM Progress] Pattern matched: safetensors 100%
[LLM Progress] Pattern matched: startup complete
[Dashboard SSE] LLM status update: status=loading, progress=67%, stage=loading_weights
[LLM Monitor] Published: loading_weights - 67% - Loading: 67%
```

## 9. 테스트 방법

1. Backend Docker 이미지 재빌드:
```bash
docker-compose -f docker-compose.dev.yml build backend
```

2. 서비스 재시작:
```bash
docker-compose -f docker-compose.dev.yml up -d backend
```

3. Dashboard에서 LLM 로딩 진행률 확인
4. Pipeline Logs 탭에서 LLM 로딩 로그 확인
5. Docker logs에서 디버그 출력 확인:
```bash
docker logs -f ev-backend
```