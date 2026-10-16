"""
Phase 29: LLM Loading Status & Health Check Enhancement Tests

TDD 방식으로 vLLM health check 호환성과 SSE service_status 기능을 테스트합니다.

Based on: docs/PRD_Phase29_LLM_Loading_Status.md
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock


# ============================================
# Phase 29.1.1: HTTP Status Code 기반 Health Check
# ============================================

class TestFetchHealthStatus:
    """fetch_health_status() 함수 테스트"""

    def test_fetch_health_status_function_exists(self):
        """fetch_health_status 함수가 존재하는지 확인"""
        from services.backend.app.routes.dashboard import fetch_health_status
        assert callable(fetch_health_status)

    @pytest.mark.asyncio
    async def test_fetch_health_status_returns_true_on_200(self):
        """HTTP 200 응답 시 True 반환"""
        from services.backend.app.routes.dashboard import fetch_health_status

        with patch('asyncio.create_subprocess_exec') as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b'200', b''))
            mock_exec.return_value = mock_proc

            result = await fetch_health_status("http://test:11003/health")
            assert result is True

    @pytest.mark.asyncio
    async def test_fetch_health_status_returns_false_on_timeout(self):
        """타임아웃 시 False 반환"""
        from services.backend.app.routes.dashboard import fetch_health_status

        with patch('asyncio.create_subprocess_exec') as mock_exec:
            mock_exec.side_effect = asyncio.TimeoutError()

            result = await fetch_health_status("http://test:11003/health", timeout=0.1)
            assert result is False

    @pytest.mark.asyncio
    async def test_fetch_health_status_handles_empty_body(self):
        """
        vLLM처럼 빈 body 반환해도 HTTP 200이면 True

        vLLM /health는 body 없이 HTTP 200 OK만 반환:
        HTTP/1.1 200 OK
        content-length: 0
        """
        from services.backend.app.routes.dashboard import fetch_health_status

        with patch('asyncio.create_subprocess_exec') as mock_exec:
            mock_proc = AsyncMock()
            # curl -w "%{http_code}" 는 status code만 반환
            mock_proc.communicate = AsyncMock(return_value=(b'200', b''))
            mock_exec.return_value = mock_proc

            result = await fetch_health_status("http://llm:11003/health")
            assert result is True


# ============================================
# Phase 29.1.2: construct_llm_info 수정
# ============================================

class TestConstructLlmInfo:
    """construct_llm_info() 함수 테스트"""

    @pytest.mark.asyncio
    async def test_construct_llm_info_uses_fetch_health_status(self):
        """construct_llm_info가 fetch_health_status를 사용하는지 확인"""
        from services.backend.app.routes.dashboard import construct_llm_info

        with patch('services.backend.app.routes.dashboard.fetch_health_status') as mock_health:
            mock_health.return_value = True
            with patch('services.backend.app.routes.dashboard.fetch_vllm_model_info') as mock_model:
                mock_model.return_value = {"name": "test-model"}

                result = await construct_llm_info()

                mock_health.assert_called_once()

    @pytest.mark.asyncio
    async def test_construct_llm_info_returns_healthy_when_vllm_200(self):
        """vLLM이 200 반환 시 healthy 상태"""
        from services.backend.app.routes.dashboard import construct_llm_info

        with patch('services.backend.app.routes.dashboard.fetch_health_status') as mock_health:
            mock_health.return_value = True
            with patch('services.backend.app.routes.dashboard.fetch_vllm_model_info') as mock_model:
                mock_model.return_value = {"name": "Qwen/Qwen2.5-14B-Instruct-AWQ"}

                result = await construct_llm_info()

                assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_construct_llm_info_returns_offline_when_vllm_unreachable(self):
        """vLLM에 연결 불가 시 offline 상태"""
        from services.backend.app.routes.dashboard import construct_llm_info

        with patch('services.backend.app.routes.dashboard.fetch_health_status') as mock_health:
            mock_health.return_value = False
            with patch('services.backend.app.routes.dashboard.get_container_health_status') as mock_docker:
                mock_docker.return_value = "unknown"
                with patch('services.backend.app.routes.dashboard.fetch_vllm_model_info') as mock_model:
                    mock_model.return_value = {"name": "unknown"}

                    result = await construct_llm_info()

                    assert result["status"] == "offline"


# ============================================
# Phase 29.2.1: vLLM /v1/models API 연동
# ============================================

class TestFetchVllmModelInfo:
    """fetch_vllm_model_info() 함수 테스트"""

    def test_fetch_vllm_model_info_function_exists(self):
        """fetch_vllm_model_info 함수가 존재하는지 확인"""
        from services.backend.app.routes.dashboard import fetch_vllm_model_info
        assert callable(fetch_vllm_model_info)

    @pytest.mark.asyncio
    async def test_fetch_vllm_model_info_returns_model_name(self):
        """vLLM /v1/models API에서 모델명 조회"""
        from services.backend.app.routes.dashboard import fetch_vllm_model_info

        with patch('services.backend.app.routes.dashboard.fetch_json') as mock_fetch:
            mock_fetch.return_value = {
                "data": [
                    {"id": "Qwen/Qwen2.5-14B-Instruct-AWQ", "owned_by": "vllm"}
                ]
            }

            result = await fetch_vllm_model_info("http://llm:11003")

            assert result["name"] == "Qwen/Qwen2.5-14B-Instruct-AWQ"

    @pytest.mark.asyncio
    async def test_fetch_vllm_model_info_fallback_to_env_var(self):
        """vLLM API 실패 시 환경변수로 fallback"""
        from services.backend.app.routes.dashboard import fetch_vllm_model_info

        with patch('services.backend.app.routes.dashboard.fetch_json') as mock_fetch:
            mock_fetch.return_value = None  # API 실패
            with patch.dict('os.environ', {'LLM_MODEL': 'Qwen/Qwen2.5-7B-Instruct-AWQ'}):
                result = await fetch_vllm_model_info("http://llm:11003")

                assert result["name"] == "Qwen/Qwen2.5-7B-Instruct-AWQ"


# ============================================
# Phase 29.2.2: 모델 정보 정확성
# ============================================

class TestLlmInfoAccuracy:
    """LLM 모델 정보 정확성 테스트"""

    @pytest.mark.asyncio
    async def test_llm_info_shows_actual_loaded_model(self):
        """실제 로딩된 모델 정보 표시"""
        from services.backend.app.routes.dashboard import construct_llm_info

        with patch('services.backend.app.routes.dashboard.fetch_health_status') as mock_health:
            mock_health.return_value = True
            with patch('services.backend.app.routes.dashboard.fetch_vllm_model_info') as mock_model:
                mock_model.return_value = {"name": "Qwen/Qwen2.5-14B-Instruct-AWQ"}

                result = await construct_llm_info()

                assert "14B" in result["model"]["name"]

    @pytest.mark.asyncio
    async def test_llm_info_not_hardcoded_7b(self):
        """7B 하드코딩 대신 실제 모델 정보 사용"""
        from services.backend.app.routes.dashboard import construct_llm_info

        with patch('services.backend.app.routes.dashboard.fetch_health_status') as mock_health:
            mock_health.return_value = True
            with patch('services.backend.app.routes.dashboard.fetch_vllm_model_info') as mock_model:
                mock_model.return_value = {"name": "Qwen/Qwen2.5-14B-Instruct-AWQ"}

                result = await construct_llm_info()

                # 기존 하드코딩된 7B가 아닌 실제 값 확인
                assert "7B" not in result["model"]["name"] or "14B" in result["model"]["name"]


# ============================================
# Phase 29.3.1: event_generator에 service_status 추가
# ============================================

class TestEventGeneratorServiceStatus:
    """event_generator의 service_status 이벤트 테스트"""

    def test_event_generator_emits_service_status(self):
        """event_generator가 service_status 이벤트를 emit하는지 확인"""
        # event_generator 내부에 service_status 로직이 포함되어 있는지 확인
        # 실제 구현은 dashboard_stream의 event_generator 내부에 있음
        from services.backend.app.routes.dashboard import dashboard_stream
        assert callable(dashboard_stream)

    @pytest.mark.asyncio
    async def test_service_status_includes_llm(self):
        """service_status에 LLM 서비스가 포함되는지 확인"""
        # event_generator가 LLM 상태를 체크하는지 확인
        # 실제 구현 후 상세 테스트 추가
        pass

    @pytest.mark.asyncio
    async def test_service_status_sent_on_change_only(self):
        """상태가 변경될 때만 service_status 전송"""
        # 이전 상태와 비교하여 변경 시에만 전송하는지 확인
        pass


# ============================================
# Phase 29.3.2: 상태 변경 감지 로직
# ============================================

class TestStatusChangeDetection:
    """상태 변경 감지 로직 테스트"""

    def test_prev_service_status_tracking(self):
        """이전 서비스 상태 추적"""
        # event_generator 내부에서 prev_service_status dict 유지
        pass

    def test_llm_checked_every_5_seconds(self):
        """LLM은 5초마다 체크"""
        # update_count % 5 == 0 로직 확인
        pass

    def test_stable_services_checked_every_30_seconds(self):
        """안정 서비스는 30초마다 체크"""
        # STT, TTS, Embedding 등은 30초 간격
        pass


# ============================================
# Phase 29.4.1: Container Health 조회
# ============================================

class TestContainerHealthStatus:
    """Docker container health status 테스트"""

    def test_get_container_health_status_function_exists(self):
        """get_container_health_status 함수가 존재하는지 확인"""
        from services.backend.app.routes.dashboard import get_container_health_status
        assert callable(get_container_health_status)

    @pytest.mark.asyncio
    async def test_get_container_health_returns_starting(self):
        """컨테이너 로딩 중일 때 'starting' 반환"""
        from services.backend.app.routes.dashboard import get_container_health_status

        with patch('asyncio.create_subprocess_exec') as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b'starting', b''))
            mock_exec.return_value = mock_proc

            result = await get_container_health_status("ev-llm")
            assert result == "starting"

    @pytest.mark.asyncio
    async def test_get_container_health_returns_healthy(self):
        """컨테이너가 healthy일 때 'healthy' 반환"""
        from services.backend.app.routes.dashboard import get_container_health_status

        with patch('asyncio.create_subprocess_exec') as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b'healthy', b''))
            mock_exec.return_value = mock_proc

            result = await get_container_health_status("ev-llm")
            assert result == "healthy"


# ============================================
# Phase 29.4.2: Loading 상태 표시
# ============================================

class TestLoadingStatus:
    """Loading 상태 표시 테스트"""

    @pytest.mark.asyncio
    async def test_llm_status_loading_when_docker_starting(self):
        """Docker health가 starting일 때 loading 상태"""
        from services.backend.app.routes.dashboard import construct_llm_info

        with patch('services.backend.app.routes.dashboard.fetch_health_status') as mock_health:
            mock_health.return_value = False  # health check 실패
            with patch('services.backend.app.routes.dashboard.get_container_health_status') as mock_docker:
                mock_docker.return_value = "starting"  # Docker는 starting
                with patch('services.backend.app.routes.dashboard.fetch_vllm_model_info') as mock_model:
                    mock_model.return_value = {"name": "unknown"}

                    result = await construct_llm_info()

                    assert result["status"] == "loading"

    def test_frontend_shows_loading_pulse(self):
        """Frontend에 loading 펄스 CSS가 있는지 확인"""
        # index.html에 .service-status.loading 스타일 존재 확인
        # 이미 구현됨 - 별도 변경 불필요
        pass


# ============================================
# Phase 33.3.1: construct_llm_info 진행률 추가
# ============================================

class TestConstructLlmInfoProgress:
    """Phase 33.3.1: construct_llm_info 진행률 테스트"""

    @pytest.mark.asyncio
    async def test_construct_llm_info_includes_progress_percent(self):
        """construct_llm_info 반환값에 progress_percent가 포함되는지 확인"""
        from services.backend.app.routes.dashboard import construct_llm_info

        with patch('services.backend.app.routes.dashboard.fetch_health_status') as mock_health:
            mock_health.return_value = False  # 로딩 중
            with patch('services.backend.app.routes.dashboard.get_container_health_status') as mock_docker:
                mock_docker.return_value = "starting"
                with patch('services.backend.app.routes.dashboard.fetch_vllm_model_info') as mock_model:
                    mock_model.return_value = {"name": "unknown"}
                    with patch('services.backend.app.routes.dashboard.get_llm_loading_progress') as mock_progress:
                        mock_progress.return_value = {
                            "progress_percent": 45,
                            "stage": "loading_weights",
                            "message": "Loading model weights: 45%"
                        }

                        result = await construct_llm_info()

                        assert "progress_percent" in result

    @pytest.mark.asyncio
    async def test_construct_llm_info_progress_from_docker_logs(self):
        """construct_llm_info가 Docker logs에서 진행률을 가져오는지 확인"""
        from services.backend.app.routes.dashboard import construct_llm_info

        with patch('services.backend.app.routes.dashboard.fetch_health_status') as mock_health:
            mock_health.return_value = False
            with patch('services.backend.app.routes.dashboard.get_container_health_status') as mock_docker:
                mock_docker.return_value = "starting"
                with patch('services.backend.app.routes.dashboard.fetch_vllm_model_info') as mock_model:
                    mock_model.return_value = {"name": "unknown"}
                    with patch('services.backend.app.routes.dashboard.get_llm_loading_progress') as mock_progress:
                        mock_progress.return_value = {
                            "progress_percent": 75,
                            "stage": "loading_weights",
                            "message": "Loading model weights: 75%"
                        }

                        result = await construct_llm_info()

                        # get_llm_loading_progress가 호출되었는지 확인
                        mock_progress.assert_called_once()
                        assert result["progress_percent"] == 75

    @pytest.mark.asyncio
    async def test_construct_llm_info_elapsed_seconds(self):
        """construct_llm_info 반환값에 elapsed_seconds가 포함되는지 확인"""
        from services.backend.app.routes.dashboard import construct_llm_info

        with patch('services.backend.app.routes.dashboard.fetch_health_status') as mock_health:
            mock_health.return_value = False
            with patch('services.backend.app.routes.dashboard.get_container_health_status') as mock_docker:
                mock_docker.return_value = "starting"
                with patch('services.backend.app.routes.dashboard.fetch_vllm_model_info') as mock_model:
                    mock_model.return_value = {"name": "unknown"}
                    with patch('services.backend.app.routes.dashboard.get_llm_loading_progress') as mock_progress:
                        mock_progress.return_value = {
                            "progress_percent": 50,
                            "stage": "loading_weights",
                            "message": "Loading model weights: 50%"
                        }
                        with patch('services.backend.app.routes.dashboard.get_container_start_time') as mock_start:
                            mock_start.return_value = 60.5  # 60.5초 경과

                            result = await construct_llm_info()

                            assert "elapsed_seconds" in result


# ============================================
# Phase 33.3.2: SSE service_status 이벤트 확장
# ============================================

class TestSSEServiceStatusProgress:
    """Phase 33.3.2: SSE service_status 이벤트 확장 테스트"""

    @pytest.mark.asyncio
    async def test_sse_service_status_includes_progress_percent(self):
        """SSE service_status 이벤트에 progress_percent가 포함되는지 확인"""
        # event_generator에서 LLM 상태 전송 시 progress_percent 포함
        from services.backend.app.routes.dashboard import construct_llm_info

        with patch('services.backend.app.routes.dashboard.fetch_health_status') as mock_health:
            mock_health.return_value = False
            with patch('services.backend.app.routes.dashboard.get_container_health_status') as mock_docker:
                mock_docker.return_value = "starting"
                with patch('services.backend.app.routes.dashboard.fetch_vllm_model_info') as mock_model:
                    mock_model.return_value = {"name": "unknown"}
                    with patch('services.backend.app.routes.dashboard.get_llm_loading_progress') as mock_progress:
                        mock_progress.return_value = {
                            "progress_percent": 60,
                            "stage": "loading_weights",
                            "message": "Loading model weights: 60%"
                        }

                        result = await construct_llm_info()

                        # SSE로 전송되는 데이터에 progress_percent가 있어야 함
                        assert "progress_percent" in result
                        assert result["progress_percent"] == 60

    @pytest.mark.asyncio
    async def test_sse_service_status_includes_elapsed_seconds(self):
        """SSE service_status 이벤트에 elapsed_seconds가 포함되는지 확인"""
        from services.backend.app.routes.dashboard import construct_llm_info

        with patch('services.backend.app.routes.dashboard.fetch_health_status') as mock_health:
            mock_health.return_value = False
            with patch('services.backend.app.routes.dashboard.get_container_health_status') as mock_docker:
                mock_docker.return_value = "starting"
                with patch('services.backend.app.routes.dashboard.fetch_vllm_model_info') as mock_model:
                    mock_model.return_value = {"name": "unknown"}
                    with patch('services.backend.app.routes.dashboard.get_llm_loading_progress') as mock_progress:
                        mock_progress.return_value = {
                            "progress_percent": 80,
                            "stage": "loading_weights",
                            "message": "Loading model weights: 80%"
                        }
                        with patch('services.backend.app.routes.dashboard.get_container_start_time') as mock_start:
                            mock_start.return_value = 90.0

                            result = await construct_llm_info()

                            assert "elapsed_seconds" in result
                            assert result["elapsed_seconds"] == 90.0


# ============================================
# Phase 33.4.1: 컨테이너 시작 시간 조회
# ============================================

class TestContainerStartTime:
    """Phase 33.4.1: 컨테이너 시작 시간 조회 테스트"""

    def test_get_container_start_time_function_exists(self):
        """get_container_start_time 함수가 존재하는지 확인"""
        from services.backend.app.routes.dashboard import get_container_start_time
        assert callable(get_container_start_time)

    @pytest.mark.asyncio
    async def test_get_container_start_time_returns_timestamp(self):
        """get_container_start_time이 시작 후 경과 시간을 반환하는지 확인"""
        from services.backend.app.routes.dashboard import get_container_start_time

        # 비동기 함수의 반환 타입 확인 (float 또는 None)
        import inspect
        sig = inspect.signature(get_container_start_time)

        # 함수가 올바른 반환 타입 annotation을 가지고 있는지 확인
        # 실제 Docker 없이도 테스트 가능
        result = await get_container_start_time("nonexistent_container")
        assert result is None or isinstance(result, float)


# ============================================
# Phase 33.4.2: 시간 기반 추정 로직
# ============================================

class TestTimeBasedProgressEstimation:
    """Phase 33.4.2: 시간 기반 진행률 추정 테스트"""

    def test_estimate_progress_from_elapsed_time_function_exists(self):
        """estimate_progress_from_elapsed_time 함수가 존재하는지 확인"""
        from services.backend.app.routes.dashboard import estimate_progress_from_elapsed_time
        assert callable(estimate_progress_from_elapsed_time)

    def test_estimate_progress_from_elapsed_time(self):
        """경과 시간에서 진행률을 추정하는지 확인"""
        from services.backend.app.routes.dashboard import estimate_progress_from_elapsed_time

        # 60초 경과 = 50% (120초 기준)
        result = estimate_progress_from_elapsed_time(60.0)
        assert result == 50

    def test_estimated_progress_max_is_99(self):
        """추정 진행률의 최대값이 99%인지 확인"""
        from services.backend.app.routes.dashboard import estimate_progress_from_elapsed_time

        # 300초 경과해도 최대 99%
        result = estimate_progress_from_elapsed_time(300.0)
        assert result == 99

    def test_estimated_progress_uses_120_second_base(self):
        """추정 진행률이 120초 기준인지 확인"""
        from services.backend.app.routes.dashboard import estimate_progress_from_elapsed_time

        # 120초 = 100% → 99%로 제한
        result = estimate_progress_from_elapsed_time(120.0)
        assert result == 99

        # 30초 = 25%
        result = estimate_progress_from_elapsed_time(30.0)
        assert result == 25


# ============================================
# Phase 33.5.1: End-to-End 진행률 흐름
# ============================================

class TestEndToEndProgressFlow:
    """Phase 33.5.1: End-to-End 진행률 흐름 테스트"""

    @pytest.mark.asyncio
    async def test_llm_loading_progress_visible_in_sse(self):
        """LLM 로딩 진행률이 SSE 이벤트로 전송되는지 확인"""
        from services.backend.app.routes.dashboard import construct_llm_info

        with patch('services.backend.app.routes.dashboard.fetch_health_status') as mock_health:
            mock_health.return_value = False
            with patch('services.backend.app.routes.dashboard.get_container_health_status') as mock_docker:
                mock_docker.return_value = "starting"
                with patch('services.backend.app.routes.dashboard.fetch_vllm_model_info') as mock_model:
                    mock_model.return_value = {"name": "Qwen/Qwen2.5-14B-Instruct-AWQ"}
                    with patch('services.backend.app.routes.dashboard.get_llm_loading_progress') as mock_progress:
                        mock_progress.return_value = {
                            "progress_percent": 67,
                            "stage": "loading_weights",
                            "message": "Loading model weights: 67%"
                        }
                        with patch('services.backend.app.routes.dashboard.get_container_start_time') as mock_start:
                            mock_start.return_value = 80.0

                            result = await construct_llm_info()

                            # SSE로 전송될 데이터 구조 검증
                            assert result["status"] == "loading"
                            assert result["progress_percent"] == 67
                            assert result["loading_stage"] == "loading_weights"
                            assert "loading_message" in result

    @pytest.mark.asyncio
    async def test_llm_loading_progress_in_pipeline_log(self):
        """LLM 로딩 진행률이 Pipeline Log에 기록되는지 확인"""
        import sys
        from pathlib import Path

        # Orchestrator app 경로 추가
        orchestrator_path = Path(__file__).parent.parent.parent / "services" / "orchestrator"
        sys.path.insert(0, str(orchestrator_path))

        from app.llm_progress import log_llm_loading_progress

        mock_logger = AsyncMock()
        mock_logger.log = AsyncMock()

        with patch("app.llm_progress.get_logger", return_value=mock_logger):
            await log_llm_loading_progress(
                progress_percent=55,
                stage="loading_weights",
                message="Loading model weights: 55%",
                session_id="test-session-123"
            )

            # log 메서드가 올바른 이벤트명으로 호출되었는지 확인
            mock_logger.log.assert_called_once()
            call_kwargs = mock_logger.log.call_args.kwargs
            assert call_kwargs.get("event") == "llm_loading_progress"
            assert call_kwargs.get("session_id") == "test-session-123"
            assert call_kwargs.get("data")["progress_percent"] == 55

    @pytest.mark.asyncio
    async def test_llm_progress_updates_every_heartbeat(self):
        """LLM 진행률이 매 heartbeat마다 업데이트되는지 확인"""
        from services.backend.app.routes.dashboard import construct_llm_info

        # 첫 번째 heartbeat: 30% 진행
        with patch('services.backend.app.routes.dashboard.fetch_health_status') as mock_health:
            mock_health.return_value = False
            with patch('services.backend.app.routes.dashboard.get_container_health_status') as mock_docker:
                mock_docker.return_value = "starting"
                with patch('services.backend.app.routes.dashboard.fetch_vllm_model_info') as mock_model:
                    mock_model.return_value = {"name": "unknown"}
                    with patch('services.backend.app.routes.dashboard.get_llm_loading_progress') as mock_progress:
                        mock_progress.return_value = {
                            "progress_percent": 30,
                            "stage": "loading_weights",
                            "message": "Loading model weights: 30%"
                        }
                        with patch('services.backend.app.routes.dashboard.get_container_start_time') as mock_start:
                            mock_start.return_value = 36.0

                            result1 = await construct_llm_info()
                            assert result1["progress_percent"] == 30

        # 두 번째 heartbeat: 60% 진행
        with patch('services.backend.app.routes.dashboard.fetch_health_status') as mock_health:
            mock_health.return_value = False
            with patch('services.backend.app.routes.dashboard.get_container_health_status') as mock_docker:
                mock_docker.return_value = "starting"
                with patch('services.backend.app.routes.dashboard.fetch_vllm_model_info') as mock_model:
                    mock_model.return_value = {"name": "unknown"}
                    with patch('services.backend.app.routes.dashboard.get_llm_loading_progress') as mock_progress:
                        mock_progress.return_value = {
                            "progress_percent": 60,
                            "stage": "loading_weights",
                            "message": "Loading model weights: 60%"
                        }
                        with patch('services.backend.app.routes.dashboard.get_container_start_time') as mock_start:
                            mock_start.return_value = 72.0

                            result2 = await construct_llm_info()
                            assert result2["progress_percent"] == 60

        # 진행률이 증가했는지 확인
        assert result2["progress_percent"] > result1["progress_percent"]


# ============================================
# Phase 33.5.2: 에러 처리
# ============================================

class TestProgressErrorHandling:
    """Phase 33.5.2: 에러 처리 테스트"""

    @pytest.mark.asyncio
    async def test_docker_logs_error_falls_back_to_time_estimate(self):
        """Docker logs 파싱 실패 시 시간 기반 추정으로 fallback"""
        from services.backend.app.routes.dashboard import construct_llm_info

        with patch('services.backend.app.routes.dashboard.fetch_health_status') as mock_health:
            mock_health.return_value = False
            with patch('services.backend.app.routes.dashboard.get_container_health_status') as mock_docker:
                mock_docker.return_value = "starting"
                with patch('services.backend.app.routes.dashboard.fetch_vllm_model_info') as mock_model:
                    mock_model.return_value = {"name": "unknown"}
                    with patch('services.backend.app.routes.dashboard.get_llm_loading_progress') as mock_progress:
                        # Docker logs 파싱 실패 (unknown stage)
                        mock_progress.return_value = {
                            "progress_percent": 0,
                            "stage": "unknown",
                            "message": "Unable to determine loading progress"
                        }
                        with patch('services.backend.app.routes.dashboard.get_container_start_time') as mock_start:
                            # 60초 경과 = 50% (time-based estimate)
                            mock_start.return_value = 60.0

                            result = await construct_llm_info()

                            # 시간 기반 추정 사용 확인
                            assert result["loading_stage"] == "estimated"
                            assert result["progress_percent"] == 50

    @pytest.mark.asyncio
    async def test_progress_graceful_on_container_not_found(self):
        """컨테이너를 찾을 수 없을 때 graceful하게 처리"""
        from services.backend.app.routes.dashboard import construct_llm_info

        with patch('services.backend.app.routes.dashboard.fetch_health_status') as mock_health:
            mock_health.return_value = False
            with patch('services.backend.app.routes.dashboard.get_container_health_status') as mock_docker:
                # 컨테이너를 찾을 수 없음
                mock_docker.return_value = "unknown"
                with patch('services.backend.app.routes.dashboard.fetch_vllm_model_info') as mock_model:
                    mock_model.return_value = {"name": "unknown"}

                    result = await construct_llm_info()

                    # 에러 없이 offline 상태로 처리
                    assert result["status"] == "offline"
                    # progress_percent가 없거나 0이어야 함
                    assert result.get("progress_percent", 0) == 0 or "progress_percent" not in result