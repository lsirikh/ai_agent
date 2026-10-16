"""
Docker Compose 테스트 Fixtures

Phase 7: Docker Compose 테스트를 위한 공통 fixture들
"""
import pytest
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from unittest.mock import Mock, AsyncMock


@dataclass
class ServiceConfig:
    """서비스 설정"""
    name: str
    image: str
    ports: List[str]
    environment: Dict[str, str]
    volumes: List[str]
    depends_on: List[str]
    healthcheck: Optional[Dict[str, Any]] = None
    deploy: Optional[Dict[str, Any]] = None


@dataclass
class ComposeConfig:
    """Docker Compose 설정"""
    version: str
    services: Dict[str, ServiceConfig]
    networks: Dict[str, Any]
    volumes: Dict[str, Any]


@pytest.fixture
def dev_compose_config() -> ComposeConfig:
    """개발 환경 Docker Compose 설정"""
    return ComposeConfig(
        version="3.8",
        services={
            "stt": ServiceConfig(
                name="stt",
                image="edgevoice/stt:dev",
                ports=["11001:11001"],
                environment={
                    "MODEL_SIZE": "large-v3",
                    "DEVICE": "cuda",
                    "COMPUTE_TYPE": "float16"
                },
                volumes=["./models/whisper:/models"],
                depends_on=[],
                healthcheck={
                    "test": ["CMD", "curl", "-f", "http://localhost:11001/health"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3
                }
            ),
            "llm": ServiceConfig(
                name="llm",
                image="edgevoice/llm:dev",
                ports=["11003:11003"],
                environment={
                    "MODEL_NAME": "Qwen/Qwen2.5-72B-Instruct-AWQ",
                    "TENSOR_PARALLEL_SIZE": "1",
                    "GPU_MEMORY_UTILIZATION": "0.9",
                    "DEVICE": "cuda"
                },
                volumes=["./models/llm:/models"],
                depends_on=[],
                healthcheck={
                    "test": ["CMD", "curl", "-f", "http://localhost:11003/health"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3
                },
                deploy={
                    "resources": {
                        "reservations": {
                            "devices": [{
                                "driver": "nvidia",
                                "count": 1,
                                "capabilities": ["gpu"]
                            }]
                        }
                    }
                }
            ),
            "tts": ServiceConfig(
                name="tts",
                image="edgevoice/tts:dev",
                ports=["11002:11002"],
                environment={
                    "MODEL_PATH": "/models/kokoro",
                    "DEVICE": "cuda"
                },
                volumes=["./models/kokoro:/models"],
                depends_on=[],
                healthcheck={
                    "test": ["CMD", "curl", "-f", "http://localhost:11002/health"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3
                }
            ),
            "embedding": ServiceConfig(
                name="embedding",
                image="edgevoice/embedding:dev",
                ports=["11004:11004"],
                environment={
                    "MODEL_NAME": "BAAI/bge-m3",
                    "DEVICE": "cuda"
                },
                volumes=["./models/embedding:/models"],
                depends_on=[],
                healthcheck={
                    "test": ["CMD", "curl", "-f", "http://localhost:11004/health"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3
                }
            ),
            "wake-word": ServiceConfig(
                name="wake-word",
                image="edgevoice/wake-word:dev",
                ports=["11005:11005"],
                environment={
                    "MODEL_PATH": "/models/openwakeword",
                    "THRESHOLD": "0.5"
                },
                volumes=["./models/openwakeword:/models"],
                depends_on=[],
                healthcheck={
                    "test": ["CMD", "curl", "-f", "http://localhost:11005/health"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3
                }
            ),
            "rag": ServiceConfig(
                name="rag",
                image="edgevoice/rag:dev",
                ports=["11006:11006"],
                environment={
                    "EMBEDDING_SERVICE_URL": "http://embedding:11004",
                    "VECTOR_DB_PATH": "/data/vectordb"
                },
                volumes=["./data/vectordb:/data/vectordb"],
                depends_on=["embedding"],
                healthcheck={
                    "test": ["CMD", "curl", "-f", "http://localhost:11006/health"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3
                }
            ),
            "orchestrator": ServiceConfig(
                name="orchestrator",
                image="edgevoice/orchestrator:dev",
                ports=["11007:11007"],
                environment={
                    "STT_SERVICE_URL": "http://stt:11001",
                    "LLM_SERVICE_URL": "http://llm:11003",
                    "TTS_SERVICE_URL": "http://tts:11002",
                    "RAG_SERVICE_URL": "http://rag:11006"
                },
                volumes=[],
                depends_on=["stt", "llm", "tts", "rag"],
                healthcheck={
                    "test": ["CMD", "curl", "-f", "http://localhost:11007/health"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3
                }
            ),
            "audio-gateway": ServiceConfig(
                name="audio-gateway",
                image="edgevoice/audio-gateway:dev",
                ports=["11008:11008"],
                environment={
                    "WAKE_WORD_SERVICE_URL": "http://wake-word:11005",
                    "ORCHESTRATOR_URL": "http://orchestrator:11007",
                    "VAD_THRESHOLD": "0.5"
                },
                volumes=[],
                depends_on=["wake-word", "orchestrator"],
                healthcheck={
                    "test": ["CMD", "curl", "-f", "http://localhost:11008/health"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3
                }
            ),
            "backend": ServiceConfig(
                name="backend",
                image="edgevoice/backend:dev",
                ports=["11000:11000"],
                environment={
                    "DATABASE_URL": "sqlite:///data/edgevoice.db",
                    "REDIS_URL": "redis://redis:6379",
                    "ORCHESTRATOR_URL": "http://orchestrator:11007",
                    "RAG_SERVICE_URL": "http://rag:11006"
                },
                volumes=["./data:/data"],
                depends_on=["redis", "orchestrator", "rag"],
                healthcheck={
                    "test": ["CMD", "curl", "-f", "http://localhost:11000/api/status"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3
                }
            ),
            "redis": ServiceConfig(
                name="redis",
                image="redis:7-alpine",
                ports=["6379:6379"],
                environment={},
                volumes=["redis-data:/data"],
                depends_on=[],
                healthcheck={
                    "test": ["CMD", "redis-cli", "ping"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3
                }
            )
        },
        networks={
            "edgevoice-net": {
                "driver": "bridge"
            }
        },
        volumes={
            "redis-data": {},
            "vectordb-data": {}
        }
    )


@pytest.fixture
def jetson_compose_config() -> ComposeConfig:
    """Jetson 배포 환경 Docker Compose 설정"""
    return ComposeConfig(
        version="3.8",
        services={
            "stt": ServiceConfig(
                name="stt",
                image="edgevoice/stt:jetson",
                ports=["11001:11001"],
                environment={
                    "MODEL_SIZE": "small",  # 경량 모델
                    "DEVICE": "cuda",
                    "COMPUTE_TYPE": "int8"  # INT8 양자화
                },
                volumes=["./models/whisper:/models"],
                depends_on=[],
                healthcheck={
                    "test": ["CMD", "curl", "-f", "http://localhost:11001/health"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3
                }
            ),
            "llm": ServiceConfig(
                name="llm",
                image="edgevoice/llm:jetson",
                ports=["11003:11003"],
                environment={
                    "MODEL_NAME": "Qwen/Qwen2.5-7B-Instruct-GPTQ-Int4",  # 경량 모델
                    "TENSOR_PARALLEL_SIZE": "1",
                    "GPU_MEMORY_UTILIZATION": "0.8",
                    "MAX_MODEL_LEN": "2048"  # 컨텍스트 길이 제한
                },
                volumes=["./models/llm:/models"],
                depends_on=[],
                healthcheck={
                    "test": ["CMD", "curl", "-f", "http://localhost:11003/health"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3
                },
                deploy={
                    "resources": {
                        "reservations": {
                            "devices": [{
                                "driver": "nvidia",
                                "count": 1,
                                "capabilities": ["gpu"]
                            }]
                        }
                    }
                }
            ),
            "tts": ServiceConfig(
                name="tts",
                image="edgevoice/tts:jetson",
                ports=["11002:11002"],
                environment={
                    "MODEL_PATH": "/models/kokoro",
                    "DEVICE": "cuda"
                },
                volumes=["./models/kokoro:/models"],
                depends_on=[],
                healthcheck={
                    "test": ["CMD", "curl", "-f", "http://localhost:11002/health"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3
                }
            ),
            "embedding": ServiceConfig(
                name="embedding",
                image="edgevoice/embedding:jetson",
                ports=["11004:11004"],
                environment={
                    "MODEL_NAME": "BAAI/bge-small-en-v1.5",  # 경량 모델
                    "DEVICE": "cuda"
                },
                volumes=["./models/embedding:/models"],
                depends_on=[],
                healthcheck={
                    "test": ["CMD", "curl", "-f", "http://localhost:11004/health"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3
                }
            ),
            "backend": ServiceConfig(
                name="backend",
                image="edgevoice/backend:jetson",
                ports=["11000:11000"],
                environment={
                    "DATABASE_URL": "sqlite:///data/edgevoice.db",
                    "REDIS_URL": "redis://redis:6379"
                },
                volumes=["./data:/data"],
                depends_on=["redis"],
                healthcheck={
                    "test": ["CMD", "curl", "-f", "http://localhost:11000/api/status"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3
                }
            ),
            "redis": ServiceConfig(
                name="redis",
                image="redis:7-alpine",
                ports=["6379:6379"],
                environment={},
                volumes=["redis-data:/data"],
                depends_on=[],
                healthcheck={
                    "test": ["CMD", "redis-cli", "ping"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3
                }
            )
        },
        networks={
            "edgevoice-net": {
                "driver": "bridge"
            }
        },
        volumes={
            "redis-data": {},
            "vectordb-data": {}
        }
    )


@pytest.fixture
def mock_docker_client():
    """Mock Docker 클라이언트"""
    client = Mock()

    # containers.list() mock
    def create_container_mock(name, status="running", health="healthy"):
        container = Mock()
        container.name = name
        container.status = status
        container.attrs = {
            "State": {
                "Health": {"Status": health} if health else {}
            },
            "NetworkSettings": {
                "Networks": {
                    "edgevoice-net": {
                        "IPAddress": f"172.18.0.{hash(name) % 255}"
                    }
                }
            },
            "Mounts": [
                {"Source": f"/host/{name}", "Destination": f"/container/{name}"}
            ]
        }
        container.exec_run = Mock(return_value=(0, b"OK"))
        return container

    containers = [
        create_container_mock("edgevoice-stt-1"),
        create_container_mock("edgevoice-llm-1"),
        create_container_mock("edgevoice-tts-1"),
        create_container_mock("edgevoice-embedding-1"),
        create_container_mock("edgevoice-wake-word-1"),
        create_container_mock("edgevoice-rag-1"),
        create_container_mock("edgevoice-orchestrator-1"),
        create_container_mock("edgevoice-audio-gateway-1"),
        create_container_mock("edgevoice-backend-1"),
        create_container_mock("edgevoice-redis-1")
    ]

    client.containers.list.return_value = containers
    client.networks.list.return_value = [Mock(name="edgevoice-net")]
    client.volumes.list.return_value = [
        Mock(name="edgevoice_redis-data"),
        Mock(name="edgevoice_vectordb-data")
    ]

    return client


@pytest.fixture
def mock_compose_project():
    """Mock Docker Compose 프로젝트"""
    project = Mock()
    project.name = "edgevoice"
    project.get_service = Mock(return_value=Mock())
    return project
