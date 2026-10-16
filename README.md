# EdgeVoice - Local AI Voice Assistant

Docker 기반의 로컬 AI 음성 비서 시스템입니다. Jetson Nano/Orin 등 임베디드 환경에서 완전히 오프라인으로 동작합니다.

## 시스템 요구사항

### 개발 환경 (Development)
- **OS**: Windows 10/11, Ubuntu 20.04+
- **RAM**: 32GB 이상
- **GPU**: NVIDIA GPU (VRAM 24GB 이상 권장)
- **Docker**: Docker Desktop 4.0+ (WSL2 백엔드)
- **CUDA**: 12.0+

### 배포 환경 (Jetson)
- **Device**: Jetson Orin Nano/NX 또는 Jetson AGX Orin
- **JetPack**: 5.1.2+
- **RAM**: 8GB 이상
- **Storage**: 64GB 이상

---

## 빠른 시작 (Quick Start)

### 1. 환경 설정

```bash
# 저장소 클론
git clone https://github.com/your-org/edgevoice.git
cd edgevoice

# 환경 변수 설정
cp .env.example .env

# .env 파일 편집 - 필수 설정 확인
# GITHUB_TOKEN, HUGGINGFACE_TOKEN 등
```

### 2. 모델 다운로드

AI 서비스 실행 전 모델을 먼저 다운로드해야 합니다:

```bash
# 모델 다운로드 스크립트 실행
./scripts/download-models.sh

# 또는 개별 모델 다운로드
# STT 모델 (Whisper)
huggingface-cli download Systran/faster-whisper-large-v3 --local-dir ./models/whisper

# LLM 모델 (Qwen)
huggingface-cli download Qwen/Qwen2.5-7B-Instruct-AWQ --local-dir ./models/qwen

# TTS 모델 (Kokoro)
huggingface-cli download hexgrad/Kokoro-82M --local-dir ./models/kokoro

# Embedding 모델 (BGE)
huggingface-cli download BAAI/bge-m3 --local-dir ./models/bge
```

### 3. 서비스 실행

#### 개발 환경 (전체 서비스)

```bash
# 인프라 서비스 먼저 실행 (Redis, PostgreSQL, ChromaDB)
docker-compose -f docker-compose.infra.yml up -d

# 잠시 대기 (DB 초기화)
sleep 10

# AI 서비스 실행
docker-compose -f docker-compose.dev.yml up -d

# 로그 확인
docker-compose -f docker-compose.dev.yml logs -f
```

#### Backend만 테스트

```bash
# Backend + Redis만 실행 (가벼운 테스트용)
docker-compose -f docker-compose.test.yml up -d

# 웹 대시보드 접속
open http://localhost:8000
```

#### Jetson 배포 환경

```bash
# Jetson용 경량 모델로 실행
docker-compose -f docker-compose.jetson.yml up -d
```

### 4. 서비스 상태 확인

```bash
# 모든 컨테이너 상태 확인
docker ps

# API 상태 확인
curl http://localhost:8000/api/status | python -m json.tool

# 개별 서비스 헬스체크
curl http://localhost:8001/health  # STT
curl http://localhost:8002/health  # LLM
curl http://localhost:8003/health  # TTS
curl http://localhost:8004/health  # Embedding
curl http://localhost:8005/health  # Audio Gateway
curl http://localhost:8006/health  # Wake Word
curl http://localhost:8007/health  # RAG
curl http://localhost:8008/health  # Orchestrator
```

---

## 서비스 포트 구성

| 서비스 | 포트 | 설명 |
|--------|------|------|
| Backend API | 8000 | 웹 대시보드 및 REST API |
| STT (Whisper) | 8001 | 음성→텍스트 변환 |
| LLM (Qwen/vLLM) | 8002 | 대화 생성 |
| TTS (Kokoro) | 8003 | 텍스트→음성 변환 |
| Embedding (BGE) | 8004 | 텍스트 임베딩 |
| Audio Gateway | 8005 | 오디오 I/O, VAD, AEC |
| Wake Word | 8006 | 웨이크 워드 감지 |
| RAG | 8007 | 문서 검색 |
| Orchestrator | 8008 | 파이프라인 조율 |
| Redis | 6379 | 이벤트 버스 |
| PostgreSQL | 5432 | 메타데이터 저장 |
| ChromaDB | 8009 | 벡터 저장소 |

---

## 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────────┐
│                        Web Dashboard                             │
│                     http://localhost:8000                        │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Backend API (FastAPI)                       │
│              /api/status, /api/settings, /api/chat               │
└─────────────────────────────────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
            ┌──────────────┐        ┌──────────────┐
            │    Redis     │◄──────►│  PostgreSQL  │
            │  (Pub/Sub)   │        │  (Metadata)  │
            └──────────────┘        └──────────────┘
                    │
        ┌───────────┼───────────┬───────────┬───────────┐
        ▼           ▼           ▼           ▼           ▼
┌─────────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│ Orchestrator│ │   STT   │ │   LLM   │ │   TTS   │ │   RAG   │
│   (State)   │ │(Whisper)│ │ (Qwen)  │ │(Kokoro) │ │  (BGE)  │
└─────────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Audio Gateway                               │
│          VAD (Silero) │ AEC │ Barge-in Detection                │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Wake Word Detector                          │
│                    (OpenWakeWord - "헤이로봇")                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 음성 대화 흐름

1. **Wake Word 감지**: "헤이로봇" 발화 → Wake Word 서비스가 감지
2. **음성 녹음**: Audio Gateway가 마이크 입력 캡처
3. **STT 변환**: Whisper 모델이 음성을 텍스트로 변환
4. **RAG 검색**: (선택) 관련 문서 컨텍스트 검색
5. **LLM 생성**: Qwen 모델이 응답 생성 (스트리밍)
6. **TTS 합성**: Kokoro가 문장 단위로 음성 합성
7. **오디오 출력**: Audio Gateway가 스피커로 출력
8. **Barge-in**: 사용자가 끼어들면 즉시 중단 후 새 입력 처리

---

## 웹 대시보드 기능

### Dashboard 탭
- 시스템 상태 모니터링
- 서비스 헬스체크 표시
- GPU 메모리 사용량

### Chat 탭
- 텍스트 기반 채팅 테스트
- 실시간 응답 스트리밍

### Knowledge Base 탭
- PDF/TXT/DOCX 문서 업로드
- RAG용 문서 관리
- 검색 테스트

### Settings 탭
- LLM 파라미터 조정 (temperature, max_tokens)
- TTS 음성 선택
- STT 언어 설정

### History 탭
- 대화 기록 조회
- JSON/CSV 내보내기

---

## 문제 해결

자세한 문제 해결 가이드는 [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)를 참조하세요.

### 빠른 진단

```bash
# 전체 시스템 상태
curl http://localhost:8000/api/status | python -m json.tool

# Docker 로그 확인
docker-compose -f docker-compose.dev.yml logs --tail=100

# 특정 서비스 로그
docker logs edgevoice-stt-1 --tail=50
docker logs edgevoice-llm-1 --tail=50
```

---

## 개발 가이드

### 테스트 실행

```bash
# 전체 테스트
python -m pytest tests/ -v

# 특정 서비스 테스트
python -m pytest tests/stt/ -v
python -m pytest tests/llm/ -v

# 통합 테스트 (서비스 실행 필요)
python -m pytest tests/integration/ -v
```

### 코드 구조

```
edgevoice/
├── services/
│   ├── stt/           # Whisper 기반 STT
│   ├── llm/           # vLLM 기반 LLM
│   ├── tts/           # Kokoro 기반 TTS
│   ├── embedding/     # BGE 임베딩
│   ├── rag/           # RAG 서비스
│   ├── wake_word/     # Wake Word 감지
│   ├── audio_gateway/ # 오디오 I/O
│   ├── orchestrator/  # 파이프라인 조율
│   └── backend/       # REST API & 대시보드
├── config/            # 설정 파일
├── models/            # AI 모델 저장소
├── scripts/           # 유틸리티 스크립트
├── tests/             # 테스트 코드
└── docs/              # 문서
```

---

## 라이선스

MIT License
