# Audio Gateway Service Dockerfile
# Phase 3.5: Audio Gateway Main
# Phase 37: Internal Microphone Support

FROM python:3.11-slim

# 환경 변수 설정
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Phase 37: 시스템 의존성 설치 (오디오 처리 + ALSA/PulseAudio)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    # PortAudio (sounddevice 백엔드)
    portaudio19-dev \
    libportaudio2 \
    libportaudiocpp0 \
    # ALSA (Linux 오디오)
    libasound2 \
    libasound2-dev \
    alsa-utils \
    # PulseAudio 클라이언트 (선택적)
    pulseaudio-utils \
    libpulse0 \
    # 오디오 파일 처리
    libsndfile1 \
    ffmpeg \
    # 네트워크 유틸리티
    curl \
    && rm -rf /var/lib/apt/lists/*

# Phase 37: ALSA 기본 설정 (no-op 방지)
RUN mkdir -p /etc/alsa && \
    echo "pcm.!default { type hw card 0 }" > /etc/asound.conf || true

# 작업 디렉토리 설정
WORKDIR /app

# 의존성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY app/ ./app/

# 포트 노출
EXPOSE 8008

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8008/health || exit 1

# 애플리케이션 실행
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8008"]
