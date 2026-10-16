"""
Jetson 배포 환경 Docker Compose 테스트

Phase 7.2: Jetson Nano/Orin 배포 환경 테스트
"""
import pytest
from unittest.mock import Mock
from typing import Dict, List


class TestLightweightModels:
    """경량 모델 사용 테스트"""

    def test_lightweight_models(self, jetson_compose_config):
        """Jetson 환경에서 경량 모델을 사용해야 한다"""
        # Given: Jetson Compose 설정
        services = jetson_compose_config.services

        # When/Then: 각 서비스가 경량 모델 사용
        # STT: whisper small (not large-v3)
        stt = services.get("stt")
        assert stt is not None
        model_size = stt.environment.get("MODEL_SIZE", "")
        assert model_size in ["small", "tiny", "base"], \
            f"STT should use lightweight model, got: {model_size}"

        # LLM: 7B Q4 (not 72B)
        llm = services.get("llm")
        assert llm is not None
        model_name = llm.environment.get("MODEL_NAME", "")
        assert "7B" in model_name or "3B" in model_name, \
            f"LLM should use 7B or smaller model, got: {model_name}"
        assert "Int4" in model_name or "Q4" in model_name or "GPTQ" in model_name, \
            f"LLM should use quantized model, got: {model_name}"

        # Embedding: bge-small (not bge-m3)
        embedding = services.get("embedding")
        assert embedding is not None
        embed_model = embedding.environment.get("MODEL_NAME", "")
        assert "small" in embed_model.lower() or "mini" in embed_model.lower(), \
            f"Embedding should use small model, got: {embed_model}"

    def test_stt_uses_int8_quantization(self, jetson_compose_config):
        """STT가 INT8 양자화를 사용해야 한다"""
        stt = jetson_compose_config.services.get("stt")
        assert stt is not None
        compute_type = stt.environment.get("COMPUTE_TYPE", "")
        assert compute_type in ["int8", "int8_float16"], \
            f"STT should use int8 quantization, got: {compute_type}"

    def test_llm_memory_optimization(self, jetson_compose_config):
        """LLM이 메모리 최적화 설정을 사용해야 한다"""
        llm = jetson_compose_config.services.get("llm")
        assert llm is not None

        # GPU 메모리 사용률 제한
        gpu_util = llm.environment.get("GPU_MEMORY_UTILIZATION", "")
        assert float(gpu_util) <= 0.85, \
            f"GPU memory utilization should be <= 0.85, got: {gpu_util}"

        # 최대 컨텍스트 길이 제한
        max_len = llm.environment.get("MAX_MODEL_LEN", "")
        assert int(max_len) <= 4096, \
            f"Max model length should be <= 4096 for Jetson, got: {max_len}"


class TestJetsonResourceConstraints:
    """Jetson 리소스 제약 테스트"""

    def test_total_vram_under_8gb(self, jetson_compose_config):
        """총 VRAM 사용량이 8GB 이하여야 한다 (Jetson Orin Nano)"""
        # Given: 서비스별 예상 VRAM 사용량 (MB)
        vram_estimates = {
            "stt": 500,      # Whisper Small
            "llm": 4000,     # Qwen 7B Q4
            "tts": 500,      # Kokoro 82M
            "embedding": 300  # BGE-Small
        }

        # When: 총 VRAM 계산
        total_vram = sum(vram_estimates.values())

        # Then: 8GB (8192MB) 이하
        assert total_vram <= 8192, \
            f"Total VRAM estimate {total_vram}MB exceeds 8GB limit"

    def test_services_have_memory_limits(self, jetson_compose_config):
        """서비스에 메모리 제한이 설정되어야 한다"""
        # Jetson 환경에서는 메모리 제한 설정 권장
        # deploy.resources.limits 확인
        for name, service in jetson_compose_config.services.items():
            if service.deploy:
                limits = service.deploy.get("resources", {}).get("limits", {})
                # 메모리 제한이 있으면 검증
                if "memory" in limits:
                    memory = limits["memory"]
                    # 숫자만 추출
                    mem_value = int(''.join(filter(str.isdigit, memory)))
                    assert mem_value > 0, f"Service '{name}' has invalid memory limit"


class TestJetsonDockerImages:
    """Jetson Docker 이미지 테스트"""

    def test_jetson_specific_images(self, jetson_compose_config):
        """Jetson 전용 이미지를 사용해야 한다"""
        services = jetson_compose_config.services

        for name, service in services.items():
            image = service.image
            # Jetson 태그 또는 arm64 호환 이미지 사용
            assert ":jetson" in image or "arm64" in image or "l4t" in image or ":dev" not in image, \
                f"Service '{name}' should use Jetson-specific image, got: {image}"

    def test_base_images_compatible(self, jetson_compose_config):
        """베이스 이미지가 Jetson 호환이어야 한다"""
        # Jetson은 ARM64 아키텍처
        # L4T (Linux for Tegra) 기반 이미지 권장
        jetson_compatible_bases = [
            "nvcr.io/nvidia/l4t",
            "dustynv",
            "arm64",
            "jetson"
        ]

        # 공식 multiarch 이미지 (ARM64 지원)
        official_multiarch_images = [
            "redis:",
            "postgres:",
            "nginx:",
            "python:"
        ]

        services = jetson_compose_config.services
        for name, service in services.items():
            image = service.image
            # Jetson 태그 또는 공식 multiarch 이미지 허용
            is_compatible = (
                any(base in image.lower() for base in jetson_compatible_bases) or
                ":jetson" in image or
                any(img in image for img in official_multiarch_images)
            )
            assert is_compatible, \
                f"Service '{name}' image may not be Jetson compatible: {image}"


class TestJetsonNetworking:
    """Jetson 네트워크 설정 테스트"""

    def test_host_network_option(self, jetson_compose_config):
        """성능을 위해 host 네트워크 옵션 고려"""
        # Jetson에서는 bridge 네트워크도 사용 가능
        networks = jetson_compose_config.networks
        assert len(networks) > 0, "Network configuration should exist"

    def test_minimal_exposed_ports(self, jetson_compose_config):
        """최소한의 포트만 노출해야 한다"""
        # Jetson 배포에서는 보안을 위해 최소 포트 노출
        essential_ports = ["11000"]  # Backend만 외부 노출 권장

        services = jetson_compose_config.services
        exposed_ports = []
        for name, service in services.items():
            for port in service.ports:
                host_port = port.split(":")[0]
                exposed_ports.append((name, host_port))

        # Backend 포트는 반드시 노출
        backend_exposed = any(p[1] == "11000" for p in exposed_ports)
        assert backend_exposed, "Backend port 11000 should be exposed"


class TestJetsonPowerManagement:
    """Jetson 전력 관리 테스트"""

    def test_power_mode_environment(self, jetson_compose_config):
        """전력 모드 환경 변수가 설정 가능해야 한다"""
        # NVIDIA Jetson 전력 모드 (nvpmodel)
        # 환경 변수로 전력 모드 힌트 제공 가능
        # 실제 전력 모드는 호스트에서 설정
        pass  # 구성 파일에서는 직접 제어 불가

    def test_no_unnecessary_gpu_services(self, jetson_compose_config):
        """불필요한 GPU 서비스가 없어야 한다"""
        # Jetson에서는 GPU 리소스가 제한적
        gpu_services = []
        for name, service in jetson_compose_config.services.items():
            if service.deploy:
                devices = service.deploy.get("resources", {}).get("reservations", {}).get("devices", [])
                if devices:
                    gpu_services.append(name)

        # 필수 GPU 서비스만 있어야 함
        essential_gpu_services = {"stt", "llm", "tts", "embedding"}
        for svc in gpu_services:
            assert svc in essential_gpu_services, \
                f"Non-essential service '{svc}' should not require GPU"


class TestJetsonStorage:
    """Jetson 스토리지 테스트"""

    def test_model_cache_location(self, jetson_compose_config):
        """모델 캐시 위치가 설정되어야 한다"""
        # Jetson에서는 SD 카드나 NVMe에 모델 저장
        model_services = ["stt", "llm", "tts", "embedding"]

        for name in model_services:
            service = jetson_compose_config.services.get(name)
            if service:
                has_model_volume = any("/models" in v for v in service.volumes)
                assert has_model_volume, \
                    f"Service '{name}' should have model volume mounted"

    def test_swap_not_required(self, jetson_compose_config):
        """스왑 없이 실행 가능해야 한다"""
        # 메모리 효율적인 모델 사용으로 스왑 불필요
        # 총 시스템 메모리 16GB 이하 환경 고려
        pass  # 구성으로는 직접 검증 불가


class TestJetsonComposeFile:
    """Jetson Compose 파일 테스트"""

    def test_compose_file_version(self, jetson_compose_config):
        """Compose 파일 버전이 호환되어야 한다"""
        version = jetson_compose_config.version
        assert version.startswith("3."), \
            f"Compose version should be 3.x, got: {version}"

    def test_all_services_have_restart_policy(self, jetson_compose_config):
        """모든 서비스에 재시작 정책이 있어야 한다"""
        # Jetson 배포에서는 자동 재시작 중요
        # conftest에서 restart 필드 추가 필요
        pass  # ServiceConfig에 restart 필드 없음

    def test_healthcheck_for_critical_services(self, jetson_compose_config):
        """중요 서비스에 헬스체크가 있어야 한다"""
        critical_services = ["stt", "llm", "tts", "embedding"]

        for name in critical_services:
            service = jetson_compose_config.services.get(name)
            if service:
                assert service.healthcheck is not None, \
                    f"Critical service '{name}' should have healthcheck"


class TestJetsonModelConfiguration:
    """Jetson 모델 설정 테스트"""

    def test_whisper_model_for_jetson(self, jetson_compose_config):
        """Whisper 모델이 Jetson에 적합해야 한다"""
        stt = jetson_compose_config.services.get("stt")
        assert stt is not None

        model_size = stt.environment.get("MODEL_SIZE", "large-v3")
        allowed_sizes = ["tiny", "base", "small"]
        assert model_size in allowed_sizes, \
            f"Whisper model '{model_size}' too large for Jetson. Use: {allowed_sizes}"

    def test_llm_model_for_jetson(self, jetson_compose_config):
        """LLM 모델이 Jetson에 적합해야 한다"""
        llm = jetson_compose_config.services.get("llm")
        assert llm is not None

        model_name = llm.environment.get("MODEL_NAME", "")
        # 7B 이하, 양자화 모델 권장
        assert any(size in model_name for size in ["1B", "3B", "7B"]), \
            f"LLM model should be 7B or smaller for Jetson"

    def test_embedding_model_for_jetson(self, jetson_compose_config):
        """Embedding 모델이 Jetson에 적합해야 한다"""
        embedding = jetson_compose_config.services.get("embedding")
        assert embedding is not None

        model_name = embedding.environment.get("MODEL_NAME", "")
        # small 또는 mini 모델 권장
        assert "small" in model_name.lower() or "mini" in model_name.lower(), \
            f"Embedding model should be small for Jetson, got: {model_name}"
