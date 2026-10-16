# EdgeVoice Wake Word Service Dockerfile
FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# OpenWakeWord 모델 다운로드 (Phase 40)
# 사전 다운로드하여 컨테이너 시작 시 모델 로드 가능하도록 함
# 지원 모델: hey_jarvis, alexa, hey_mycroft
RUN python -c "import openwakeword; openwakeword.utils.download_models()"

# 앱 복사
COPY app/ ./app/

# 환경 변수 설정
ENV PYTHONPATH=/app
ENV WAKE_WORD_ENVIRONMENT=development
ENV REDIS_HOST=redis
ENV REDIS_PORT=6379
ENV WAKE_WORD_THRESHOLD=0.3

# 포트 노출
EXPOSE 8005

# 실행 (FastAPI with uvicorn)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
