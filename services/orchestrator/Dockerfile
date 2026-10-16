# EdgeVoice Orchestrator Service Dockerfile
FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 복사
COPY app/ ./app/

# 환경 변수 설정
ENV PYTHONPATH=/app
ENV ORCHESTRATOR_ENVIRONMENT=development

# 포트 노출
EXPOSE 8007

# 실행 (FastAPI with uvicorn)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8007"]
