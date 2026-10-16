# EdgeVoice STT Service Dockerfile
# Faster-Whisper 기반 음성 인식 서비스

FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

# 환경 변수 설정
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV MODEL_SIZE=large-v3-turbo
ENV COMPUTE_TYPE=float16
ENV LANGUAGE=ko
ENV STT_ENVIRONMENT=development

# apt 동작 안정화 설정 (재시도 / 타임아웃 / 캐시 비활성화)
RUN set -eux; \
    echo 'Acquire::Retries "3";' > /etc/apt/apt.conf.d/80-retries; \
    echo 'Acquire::http::Timeout "30";' >> /etc/apt/apt.conf.d/80-retries; \
    echo 'Acquire::http::Pipeline-Depth "0";' > /etc/apt/apt.conf.d/90-no-pipeline; \
    echo 'Acquire::http::No-Cache "true";' >> /etc/apt/apt.conf.d/90-no-pipeline

# 시스템 패키지 설치 (캐시 삭제 + update 3번까지 재시도)
RUN set -eux; \
    rm -rf /var/lib/apt/lists/*; \
    apt-get clean; \
    for i in 1 2 3; do \
        if apt-get update -o Acquire::http::No-Cache=true; then \
            break; \
        fi; \
        echo "apt-get update failed, retrying ($i/3)..."; \
        sleep 5; \
    done; \
    apt-get install -y --no-install-recommends \
        python3.11 \
        python3-pip \
        python3.11-dev \
        ffmpeg \
        curl \
    ; \
    rm -rf /var/lib/apt/lists/*

# # 시스템 패키지 설치
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     python3.11 \
#     python3-pip \
#     python3.11-dev \
#     ffmpeg \
#     curl \
#     && rm -rf /var/lib/apt/lists/*

# Python 심볼릭 링크
RUN ln -sf /usr/bin/python3.11 /usr/bin/python

# 작업 디렉토리 설정
WORKDIR /app

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY app/ ./app/

# 모델 캐시 디렉토리
RUN mkdir -p /app/models

# 포트 노출
EXPOSE 8001

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# 실행
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
