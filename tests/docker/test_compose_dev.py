"""
개발 환경 Docker Compose 테스트

Phase 7.1: 개발 환경 Docker Compose 설정 테스트
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, List, Any
import yaml


class TestAllServicesHealthy:
    """모든 서비스 헬스체크 테스트"""

    def test_all_services_healthy(self, dev_compose_config, mock_docker_client):
        """모든 서비스가 healthy 상태여야 한다"""
        # Given: Docker Compose로 실행된 서비스들
        containers = mock_docker_client.containers.list()

        # When: 각 서비스의 헬스 상태 확인
        unhealthy_services = []
        for container in containers:
            health_status = container.attrs.get("State", {}).get("Health", {}).get("Status")
            if health_status != "healthy":
                unhealthy_services.append(container.name)

        # Then: 모든 서비스가 healthy
        assert len(unhealthy_services) == 0, f"Unhealthy services: {unhealthy_services}"

    def test_all_required_services_running(self, dev_compose_config, mock_docker_client):
        """필수 서비스가 모두 실행 중이어야 한다"""
        # Given: 필수 서비스 목록
        required_services = [
            "stt", "llm", "tts", "embedding",
            "wake-word", "rag", "orchestrator",
            "audio-gateway", "backend", "redis"
        ]

        # When: 실행 중인 컨테이너 목록 확인
        containers = mock_docker_client.containers.list()
        running_services = [c.name for c in containers if c.status == "running"]

        # Then: 모든 필수 서비스가 실행 중
        for service in required_services:
            found = any(service in name for name in running_services)
            assert found, f"Required service '{service}' is not running"

    def test_services_have_healthcheck_configured(self, dev_compose_config):
        """모든 서비스에 헬스체크가 설정되어야 한다"""
        # Given: Docker Compose 설정
        services = dev_compose_config.services

        # When/Then: 각 서비스에 헬스체크 확인
        for name, config in services.items():
            assert config.healthcheck is not None, \
                f"Service '{name}' has no healthcheck configured"
            assert "test" in config.healthcheck, \
                f"Service '{name}' healthcheck has no test command"

    def test_healthcheck_intervals_appropriate(self, dev_compose_config):
        """헬스체크 간격이 적절해야 한다"""
        # Given: Docker Compose 설정
        services = dev_compose_config.services

        # When/Then: 헬스체크 설정 확인
        for name, config in services.items():
            if config.healthcheck:
                interval = config.healthcheck.get("interval", "30s")
                timeout = config.healthcheck.get("timeout", "10s")
                retries = config.healthcheck.get("retries", 3)

                # 간격은 30초 이하
                assert interval in ["10s", "15s", "20s", "30s"], \
                    f"Service '{name}' has too long healthcheck interval: {interval}"
                # 재시도는 3회 이상
                assert retries >= 3, \
                    f"Service '{name}' has too few retries: {retries}"


class TestNetworkConnectivity:
    """서비스 간 네트워크 연결 테스트"""

    def test_network_connectivity(self, mock_docker_client):
        """서비스 간 네트워크 연결이 되어야 한다"""
        # Given: 실행 중인 컨테이너들
        containers = mock_docker_client.containers.list()

        # When: 각 컨테이너의 네트워크 설정 확인
        network_issues = []
        for container in containers:
            networks = container.attrs.get("NetworkSettings", {}).get("Networks", {})
            if "edgevoice-net" not in networks:
                network_issues.append(f"{container.name}: not in edgevoice-net")

        # Then: 모든 컨테이너가 같은 네트워크에 연결
        assert len(network_issues) == 0, f"Network issues: {network_issues}"

    def test_service_dns_resolution(self, mock_docker_client):
        """서비스 DNS 해석이 되어야 한다"""
        # Given: 서비스 이름 목록
        service_names = ["stt", "llm", "tts", "embedding", "redis"]

        # When: DNS 해석 테스트 (mock)
        containers = mock_docker_client.containers.list()
        backend_container = next(
            (c for c in containers if "backend" in c.name), None
        )

        # Then: 각 서비스 이름으로 ping 가능
        for service in service_names:
            # Mock exec_run returns (exit_code, output)
            exit_code, _ = backend_container.exec_run(f"ping -c 1 {service}")
            assert exit_code == 0, f"Cannot resolve DNS for service: {service}"

    def test_internal_ports_accessible(self, dev_compose_config):
        """내부 포트가 접근 가능해야 한다"""
        # Given: 서비스별 내부 포트
        expected_ports = {
            "stt": "11001",
            "tts": "11002",
            "llm": "11003",
            "embedding": "11004",
            "wake-word": "11005",
            "rag": "11006",
            "orchestrator": "11007",
            "audio-gateway": "11008",
            "backend": "11000",
            "redis": "6379"
        }

        # When/Then: 각 서비스의 포트 설정 확인
        for service_name, expected_port in expected_ports.items():
            service = dev_compose_config.services.get(service_name)
            assert service is not None, f"Service '{service_name}' not found"
            assert any(expected_port in p for p in service.ports), \
                f"Service '{service_name}' does not expose port {expected_port}"

    def test_service_dependencies_configured(self, dev_compose_config):
        """서비스 의존성이 올바르게 설정되어야 한다"""
        # Given: 예상 의존성
        expected_dependencies = {
            "rag": ["embedding"],
            "orchestrator": ["stt", "llm", "tts", "rag"],
            "audio-gateway": ["wake-word", "orchestrator"],
            "backend": ["redis", "orchestrator", "rag"]
        }

        # When/Then: 의존성 확인
        for service_name, deps in expected_dependencies.items():
            service = dev_compose_config.services.get(service_name)
            assert service is not None, f"Service '{service_name}' not found"
            for dep in deps:
                assert dep in service.depends_on, \
                    f"Service '{service_name}' should depend on '{dep}'"


class TestVolumesMounted:
    """볼륨 마운트 테스트"""

    def test_volumes_mounted(self, mock_docker_client):
        """볼륨이 올바르게 마운트되어야 한다"""
        # Given: 실행 중인 컨테이너들
        containers = mock_docker_client.containers.list()

        # When: 각 컨테이너의 마운트 정보 확인
        mount_issues = []
        for container in containers:
            mounts = container.attrs.get("Mounts", [])
            if not mounts:
                # redis는 named volume 사용
                if "redis" not in container.name:
                    mount_issues.append(f"{container.name}: no mounts")

        # Then: 필요한 볼륨이 마운트됨
        # 일부 서비스는 마운트가 없을 수 있음 (orchestrator 등)
        assert len(mount_issues) < 5, f"Mount issues: {mount_issues}"

    def test_model_volumes_configured(self, dev_compose_config):
        """모델 볼륨이 설정되어야 한다"""
        # Given: 모델이 필요한 서비스
        model_services = ["stt", "llm", "tts", "embedding", "wake-word"]

        # When/Then: 각 서비스의 볼륨 설정 확인
        for service_name in model_services:
            service = dev_compose_config.services.get(service_name)
            assert service is not None, f"Service '{service_name}' not found"
            assert len(service.volumes) > 0, \
                f"Service '{service_name}' has no volumes for models"
            # 모델 디렉토리가 마운트되어야 함
            has_model_volume = any("/models" in v for v in service.volumes)
            assert has_model_volume, \
                f"Service '{service_name}' has no model volume mounted"

    def test_data_persistence_volumes(self, dev_compose_config):
        """데이터 영속성 볼륨이 설정되어야 한다"""
        # Given: 데이터 영속성이 필요한 서비스
        data_services = {
            "redis": "redis-data",
            "rag": "vectordb",
            "backend": "/data"
        }

        # When/Then: 데이터 볼륨 확인
        for service_name, volume_pattern in data_services.items():
            service = dev_compose_config.services.get(service_name)
            assert service is not None, f"Service '{service_name}' not found"
            has_data_volume = any(volume_pattern in v for v in service.volumes)
            assert has_data_volume, \
                f"Service '{service_name}' has no data persistence volume"

    def test_volume_permissions(self, mock_docker_client):
        """볼륨 권한이 올바르게 설정되어야 한다"""
        # Given: 실행 중인 컨테이너들
        containers = mock_docker_client.containers.list()

        # When: 볼륨 쓰기 권한 테스트 (mock)
        for container in containers:
            mounts = container.attrs.get("Mounts", [])
            for mount in mounts:
                destination = mount.get("Destination", "")
                # Mock: 쓰기 테스트
                exit_code, _ = container.exec_run(f"touch {destination}/test_write")
                assert exit_code == 0, \
                    f"Cannot write to volume {destination} in {container.name}"


class TestEnvironmentVariables:
    """환경 변수 테스트"""

    def test_required_env_vars_set(self, dev_compose_config):
        """필수 환경 변수가 설정되어야 한다"""
        # Given: 서비스별 필수 환경 변수
        required_vars = {
            "stt": ["MODEL_SIZE", "DEVICE"],
            "llm": ["MODEL_NAME", "TENSOR_PARALLEL_SIZE"],
            "tts": ["MODEL_PATH", "DEVICE"],
            "embedding": ["MODEL_NAME", "DEVICE"],
            "backend": ["DATABASE_URL", "REDIS_URL"]
        }

        # When/Then: 환경 변수 확인
        for service_name, vars_list in required_vars.items():
            service = dev_compose_config.services.get(service_name)
            assert service is not None, f"Service '{service_name}' not found"
            for var in vars_list:
                assert var in service.environment, \
                    f"Service '{service_name}' missing env var: {var}"

    def test_service_urls_configured(self, dev_compose_config):
        """서비스 URL이 올바르게 설정되어야 한다"""
        # Given: URL 설정이 필요한 서비스
        url_configs = {
            "rag": {"EMBEDDING_SERVICE_URL": "http://embedding:11004"},
            "orchestrator": {
                "STT_SERVICE_URL": "http://stt:11001",
                "LLM_SERVICE_URL": "http://llm:11003",
                "TTS_SERVICE_URL": "http://tts:11002"
            },
            "backend": {
                "ORCHESTRATOR_URL": "http://orchestrator:11007",
                "RAG_SERVICE_URL": "http://rag:11006"
            }
        }

        # When/Then: URL 설정 확인
        for service_name, urls in url_configs.items():
            service = dev_compose_config.services.get(service_name)
            assert service is not None, f"Service '{service_name}' not found"
            for var, expected_url in urls.items():
                assert var in service.environment, \
                    f"Service '{service_name}' missing URL env var: {var}"
                assert service.environment[var] == expected_url, \
                    f"Service '{service_name}' has wrong URL for {var}"


class TestGPUConfiguration:
    """GPU 설정 테스트"""

    def test_gpu_services_have_deploy_config(self, dev_compose_config):
        """GPU 서비스에 deploy 설정이 있어야 한다"""
        # Given: GPU가 필요한 서비스
        gpu_services = ["llm"]  # LLM은 반드시 GPU 필요

        # When/Then: deploy 설정 확인
        for service_name in gpu_services:
            service = dev_compose_config.services.get(service_name)
            assert service is not None, f"Service '{service_name}' not found"
            assert service.deploy is not None, \
                f"Service '{service_name}' has no deploy configuration"

            # GPU reservation 확인
            resources = service.deploy.get("resources", {})
            reservations = resources.get("reservations", {})
            devices = reservations.get("devices", [])
            assert len(devices) > 0, \
                f"Service '{service_name}' has no GPU device reservation"

            # nvidia driver 확인
            gpu_device = devices[0]
            assert gpu_device.get("driver") == "nvidia", \
                f"Service '{service_name}' GPU driver is not nvidia"

    def test_cuda_device_environment(self, dev_compose_config):
        """CUDA 장치 환경 변수가 설정되어야 한다"""
        # Given: CUDA 사용 서비스
        cuda_services = ["stt", "llm", "tts", "embedding"]

        # When/Then: DEVICE 환경 변수 확인
        for service_name in cuda_services:
            service = dev_compose_config.services.get(service_name)
            assert service is not None, f"Service '{service_name}' not found"
            device = service.environment.get("DEVICE", "")
            assert device == "cuda", \
                f"Service '{service_name}' DEVICE should be 'cuda', got '{device}'"


class TestComposeFileGeneration:
    """Docker Compose 파일 생성 테스트"""

    def test_compose_file_valid_yaml(self, dev_compose_config):
        """생성된 Compose 파일이 유효한 YAML이어야 한다"""
        # Given: Compose 설정
        compose_dict = {
            "version": dev_compose_config.version,
            "services": {},
            "networks": dev_compose_config.networks,
            "volumes": dev_compose_config.volumes
        }

        for name, service in dev_compose_config.services.items():
            compose_dict["services"][name] = {
                "image": service.image,
                "ports": service.ports,
                "environment": service.environment,
                "volumes": service.volumes
            }
            if service.depends_on:
                compose_dict["services"][name]["depends_on"] = service.depends_on
            if service.healthcheck:
                compose_dict["services"][name]["healthcheck"] = service.healthcheck
            if service.deploy:
                compose_dict["services"][name]["deploy"] = service.deploy

        # When: YAML 직렬화
        yaml_content = yaml.dump(compose_dict, default_flow_style=False)

        # Then: YAML 파싱 가능
        parsed = yaml.safe_load(yaml_content)
        assert parsed is not None
        assert "services" in parsed
        assert len(parsed["services"]) == len(dev_compose_config.services)

    def test_compose_version_compatible(self, dev_compose_config):
        """Compose 파일 버전이 호환 가능해야 한다"""
        # Given: Compose 버전
        version = dev_compose_config.version

        # Then: 3.x 버전이어야 함
        assert version.startswith("3."), \
            f"Compose version should be 3.x, got {version}"
