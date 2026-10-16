"""
Test Project Structure

TDD Phase 0.1: 프로젝트 필수 디렉토리 구조 존재 확인
"""
import os
from pathlib import Path

import pytest


# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent


class TestProjectStructure:
    """프로젝트 구조 테스트"""

    # PRD에 정의된 필수 디렉토리 목록
    REQUIRED_DIRECTORIES = [
        "services",
        "services/audio_gateway",
        "services/wake_word",
        "services/stt",
        "services/tts",
        "services/embedding",
        "services/orchestrator",
        "services/backend",
        "services/web-ui",
        "config",
        "config/postgres",
        "models",
        "scripts",
        "data",
        "data/knowledge",
        "tests",
    ]

    REQUIRED_SERVICE_SUBDIRS = [
        "services/audio_gateway/app",
        "services/wake_word/app",
        "services/stt/app",
        "services/tts/app",
        "services/embedding/app",
        "services/orchestrator/app",
        "services/backend/app",
        "services/backend/app/routes",
        "services/web-ui/src",
        "services/web-ui/src/pages",
    ]

    def test_project_root_exists(self):
        """프로젝트 루트 디렉토리가 존재해야 한다"""
        assert PROJECT_ROOT.exists(), f"Project root not found: {PROJECT_ROOT}"

    @pytest.mark.parametrize("directory", REQUIRED_DIRECTORIES)
    def test_required_directory_exists(self, directory: str):
        """필수 디렉토리가 존재해야 한다"""
        dir_path = PROJECT_ROOT / directory
        assert dir_path.exists(), f"Required directory not found: {directory}"
        assert dir_path.is_dir(), f"Path is not a directory: {directory}"

    @pytest.mark.parametrize("directory", REQUIRED_SERVICE_SUBDIRS)
    def test_service_subdirectory_exists(self, directory: str):
        """서비스 하위 디렉토리가 존재해야 한다"""
        dir_path = PROJECT_ROOT / directory
        assert dir_path.exists(), f"Service subdirectory not found: {directory}"
        assert dir_path.is_dir(), f"Path is not a directory: {directory}"

    def test_services_have_init_files(self):
        """각 서비스의 app 디렉토리에 __init__.py가 존재해야 한다"""
        services = [
            "audio_gateway",
            "wake_word",
            "stt",
            "tts",
            "embedding",
            "orchestrator",
            "backend",
        ]
        for service in services:
            init_file = PROJECT_ROOT / "services" / service / "app" / "__init__.py"
            assert init_file.exists(), f"Missing __init__.py in {service}/app"

    def test_tests_directory_has_init(self):
        """tests 디렉토리에 __init__.py가 존재해야 한다"""
        init_file = PROJECT_ROOT / "tests" / "__init__.py"
        assert init_file.exists(), "Missing __init__.py in tests directory"
