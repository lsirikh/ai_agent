"""
Docker Pipeline Integration Tests

Phase 8.6: Docker 환경에서 파이프라인 연동 테스트
"""
import os

import pytest
import yaml


class TestTTSRedisEnvVars:
    """TTS 서비스 Redis 환경변수 테스트"""

    def test_tts_has_redis_env_vars(self):
        """docker-compose.dev.yml에서 TTS 서비스가 Redis 환경변수를 가지고 있는지 테스트"""
        compose_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..",
            "docker-compose.dev.yml"
        )

        with open(compose_path, "r", encoding="utf-8") as f:
            compose = yaml.safe_load(f)

        # TTS 서비스 확인
        assert "tts" in compose.get("services", {}), "TTS service not found"

        tts_service = compose["services"]["tts"]

        # 환경변수 확인
        env_vars = tts_service.get("environment", {})

        # dict 또는 list 형식 모두 처리
        if isinstance(env_vars, list):
            env_dict = {}
            for item in env_vars:
                if "=" in item:
                    key, value = item.split("=", 1)
                    env_dict[key] = value
            env_vars = env_dict

        # REDIS_HOST, REDIS_PORT, REDIS_ENABLED 확인
        assert "REDIS_HOST" in env_vars or any(
            "REDIS_HOST" in str(v) for v in env_vars.values()
        ), "REDIS_HOST not found in TTS environment"

    def test_tts_depends_on_redis(self):
        """TTS 서비스가 Redis에 의존하는지 테스트"""
        compose_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..",
            "docker-compose.dev.yml"
        )

        with open(compose_path, "r", encoding="utf-8") as f:
            compose = yaml.safe_load(f)

        tts_service = compose["services"]["tts"]

        # depends_on 확인
        depends_on = tts_service.get("depends_on", [])

        # dict 또는 list 형식 모두 처리
        if isinstance(depends_on, dict):
            assert "redis" in depends_on, "TTS should depend on redis"
        else:
            assert "redis" in depends_on, "TTS should depend on redis"


class TestOrchestratorRedisEnvVars:
    """Orchestrator 서비스 Redis 환경변수 테스트"""

    def test_orchestrator_has_redis_env_vars(self):
        """Orchestrator 서비스가 Redis 환경변수를 가지고 있는지 테스트"""
        compose_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..",
            "docker-compose.dev.yml"
        )

        with open(compose_path, "r", encoding="utf-8") as f:
            compose = yaml.safe_load(f)

        assert "orchestrator" in compose.get("services", {}), "Orchestrator service not found"

        orchestrator_service = compose["services"]["orchestrator"]
        env_vars = orchestrator_service.get("environment", {})

        if isinstance(env_vars, list):
            env_dict = {}
            for item in env_vars:
                if "=" in item:
                    key, value = item.split("=", 1)
                    env_dict[key] = value
            env_vars = env_dict

        assert "REDIS_HOST" in env_vars or any(
            "REDIS_HOST" in str(v) for v in env_vars.values()
        ), "REDIS_HOST not found in Orchestrator environment"


class TestRedisNetworkConnectivity:
    """Redis 네트워크 연결 테스트"""

    def test_services_on_same_network(self):
        """TTS, Orchestrator, Redis가 같은 네트워크에 있는지 테스트"""
        compose_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..",
            "docker-compose.dev.yml"
        )

        with open(compose_path, "r", encoding="utf-8") as f:
            compose = yaml.safe_load(f)

        services = compose.get("services", {})

        # 각 서비스의 네트워크 확인
        def get_networks(service):
            networks = service.get("networks", [])
            if isinstance(networks, dict):
                return list(networks.keys())
            return networks

        redis_networks = get_networks(services.get("redis", {}))
        tts_networks = get_networks(services.get("tts", {}))
        orchestrator_networks = get_networks(services.get("orchestrator", {}))

        # 공통 네트워크 확인 (또는 networks가 지정되지 않은 경우 기본 네트워크 사용)
        if redis_networks and tts_networks:
            common = set(redis_networks) & set(tts_networks)
            assert len(common) > 0 or not redis_networks, "TTS and Redis should share a network"

        if redis_networks and orchestrator_networks:
            common = set(redis_networks) & set(orchestrator_networks)
            assert len(common) > 0 or not redis_networks, "Orchestrator and Redis should share a network"


class TestDockerComposeValidity:
    """Docker Compose 파일 유효성 테스트"""

    def test_docker_compose_valid_yaml(self):
        """docker-compose.dev.yml이 유효한 YAML인지 테스트"""
        compose_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..",
            "docker-compose.dev.yml"
        )

        with open(compose_path, "r", encoding="utf-8") as f:
            compose = yaml.safe_load(f)

        assert compose is not None
        assert "services" in compose
        assert len(compose["services"]) > 0

    def test_required_services_exist(self):
        """필수 서비스들이 정의되어 있는지 테스트"""
        compose_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..",
            "docker-compose.dev.yml"
        )

        with open(compose_path, "r", encoding="utf-8") as f:
            compose = yaml.safe_load(f)

        required_services = ["redis", "tts", "orchestrator", "stt"]
        services = compose.get("services", {})

        for service in required_services:
            assert service in services, f"Required service '{service}' not found"
