# EdgeVoice TTS Service Dockerfile
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

# APT 안정성 설정: 재시도 및 타임아웃
RUN echo 'Acquire::Retries "3";' > /etc/apt/apt.conf.d/80-retries && \
    echo 'Acquire::http::Timeout "30";' >> /etc/apt/apt.conf.d/80-retries

# Python 설치 (캐시 정리 후 설치로 Hash Sum mismatch 방지)
RUN rm -rf /var/lib/apt/lists/* && \
    apt-get clean && \
    apt-get update --fix-missing && \
    apt-get install -y --no-install-recommends \
        python3.11 \
        python3-pip \
        python3.11-venv \
        libsndfile1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 작업 디렉토리 설정
WORKDIR /app

# pip 업그레이드
RUN pip3 install --upgrade pip

# 의존성 설치
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# 앱 복사
COPY app/ ./app/

# 환경 변수 설정
ENV PYTHONPATH=/app
ENV TTS_ENVIRONMENT=development

# 포트 노출
EXPOSE 8002

# 실행
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
