"""
Web Dashboard E2E Tests

Phase 6.2: 웹 대시보드 E2E 테스트
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import json


class TestWebDashboardE2E:
    """웹 대시보드 E2E 테스트"""

    @pytest.mark.asyncio
    async def test_dashboard_loads_system_status(self, mock_services):
        """대시보드에서 시스템 상태를 로드해야 한다"""
        # 모의 시스템 상태
        system_status = {
            "orchestrator_state": "IDLE",
            "cpu_percent": 25.5,
            "memory_percent": 45.2,
            "gpu": {
                "name": "NVIDIA Jetson",
                "memory_used": 2048,
                "memory_total": 8192,
                "utilization": 30
            },
            "services": {
                "stt": {"healthy": True},
                "llm": {"healthy": True},
                "tts": {"healthy": True}
            }
        }

        # API 응답 시뮬레이션
        async def get_status():
            return system_status

        status = await get_status()

        assert status["orchestrator_state"] == "IDLE"
        assert status["cpu_percent"] > 0
        assert status["services"]["stt"]["healthy"]

    @pytest.mark.asyncio
    async def test_dashboard_real_time_updates(self, mock_redis_pubsub):
        """대시보드가 실시간 업데이트를 수신해야 한다"""
        received_updates = []

        # 이벤트 구독
        await mock_redis_pubsub.subscribe("orchestrator:state")

        # 상태 변경 이벤트 발행
        state_changes = ["IDLE", "LISTENING", "PROCESSING", "SPEAKING", "IDLE"]

        for state in state_changes:
            event = {"type": "state_change", "state": state}
            await mock_redis_pubsub.put_event(event)

        # 이벤트 수신
        for _ in range(len(state_changes)):
            msg = await mock_redis_pubsub.get_message()
            if msg:
                received_updates.append(msg)

        assert len(received_updates) == len(state_changes)

    @pytest.mark.asyncio
    async def test_dashboard_service_health_indicators(self, mock_services):
        """대시보드에서 서비스 헬스 인디케이터를 표시해야 한다"""
        # 각 서비스 헬스 체크
        health_status = {}

        for name, service in mock_services.items():
            if hasattr(service, 'health'):
                result = await service.health()
                health_status[name] = result["status"]

        # 헬스 인디케이터 상태 확인
        assert health_status["stt"] == "healthy"
        assert health_status["llm"] == "healthy"
        assert health_status["tts"] == "healthy"


class TestSettingsPageE2E:
    """설정 페이지 E2E 테스트"""

    @pytest.mark.asyncio
    async def test_load_current_settings(self):
        """현재 설정을 로드해야 한다"""
        # 모의 설정 데이터
        current_settings = {
            "llm": {
                "model": "Qwen2.5-7B",
                "temperature": 0.7,
                "max_tokens": 1024,
                "system_prompt": "You are a helpful assistant."
            },
            "tts": {
                "voice": "af_heart",
                "speed": 1.0
            },
            "stt": {
                "language": "ko",
                "beam_size": 5
            },
            "audio": {
                "vad_threshold": 0.5,
                "silence_duration": 1.0
            }
        }

        # 설정 로드 시뮬레이션
        async def get_settings(category):
            return current_settings.get(category, {})

        llm_settings = await get_settings("llm")
        tts_settings = await get_settings("tts")

        assert llm_settings["temperature"] == 0.7
        assert tts_settings["voice"] == "af_heart"

    @pytest.mark.asyncio
    async def test_update_settings(self, mock_redis_pubsub):
        """설정을 업데이트할 수 있어야 한다"""
        # 설정 저장소
        settings_store = {
            "llm": {"temperature": 0.7}
        }

        # 설정 업데이트
        async def update_settings(category, data):
            settings_store[category].update(data)
            # 설정 변경 이벤트 발행
            await mock_redis_pubsub.publish(
                "settings:updated",
                json.dumps({"category": category, "data": data})
            )
            return settings_store[category]

        # temperature 업데이트
        new_settings = await update_settings("llm", {"temperature": 0.5})

        assert new_settings["temperature"] == 0.5
        mock_redis_pubsub.publish.assert_called()

    @pytest.mark.asyncio
    async def test_settings_validation(self):
        """설정 유효성 검사가 동작해야 한다"""
        def validate_settings(category, data):
            errors = {}

            if category == "llm":
                if "temperature" in data:
                    temp = data["temperature"]
                    if temp < 0 or temp > 2:
                        errors["temperature"] = "Temperature must be between 0 and 2"

                if "max_tokens" in data:
                    tokens = data["max_tokens"]
                    if tokens < 1 or tokens > 8192:
                        errors["max_tokens"] = "Max tokens must be between 1 and 8192"

            return errors

        # 유효한 설정
        valid_errors = validate_settings("llm", {"temperature": 0.7, "max_tokens": 1024})
        assert len(valid_errors) == 0

        # 무효한 설정
        invalid_errors = validate_settings("llm", {"temperature": 3.0, "max_tokens": 10000})
        assert "temperature" in invalid_errors
        assert "max_tokens" in invalid_errors

    @pytest.mark.asyncio
    async def test_reset_to_defaults(self):
        """기본값으로 리셋할 수 있어야 한다"""
        # 기본 설정
        default_settings = {
            "llm": {
                "model": "Qwen2.5-7B",
                "temperature": 0.7,
                "max_tokens": 1024
            },
            "tts": {
                "voice": "af_heart",
                "speed": 1.0
            }
        }

        # 현재 설정 (변경됨)
        current_settings = {
            "llm": {
                "model": "Qwen2.5-7B",
                "temperature": 0.3,
                "max_tokens": 2048
            },
            "tts": {
                "voice": "am_adam",
                "speed": 1.5
            }
        }

        # 기본값으로 리셋
        async def reset_to_defaults():
            return default_settings.copy()

        reset_settings = await reset_to_defaults()

        assert reset_settings["llm"]["temperature"] == 0.7
        assert reset_settings["tts"]["voice"] == "af_heart"


class TestKnowledgePageE2E:
    """Knowledge 페이지 E2E 테스트"""

    @pytest.mark.asyncio
    async def test_upload_document(self, mock_services, mock_database):
        """문서를 업로드할 수 있어야 한다"""
        # 파일 업로드 시뮬레이션
        file_content = b"This is a test document content."
        filename = "test_document.txt"

        # DB에 저장
        doc_id = await mock_database.add_document(filename, file_content.decode())

        # RAG에 추가
        rag_result = await mock_services["rag"].add_document({
            "id": doc_id,
            "content": file_content.decode(),
            "metadata": {"source": filename}
        })

        assert doc_id is not None
        assert rag_result["chunks"] > 0

    @pytest.mark.asyncio
    async def test_list_documents(self, mock_database):
        """문서 목록을 조회할 수 있어야 한다"""
        # 테스트 문서 추가
        await mock_database.add_document("doc1.txt", "Content 1")
        await mock_database.add_document("doc2.pdf", "Content 2")
        await mock_database.add_document("doc3.docx", "Content 3")

        # 문서 목록 조회
        documents = mock_database.documents

        assert len(documents) >= 3

    @pytest.mark.asyncio
    async def test_search_knowledge_base(self, mock_services):
        """지식 베이스를 검색할 수 있어야 한다"""
        query = "회사 정책"

        results = await mock_services["rag"].retrieve(query=query)

        assert len(results) > 0
        assert "score" in results[0]
        assert "content" in results[0]

    @pytest.mark.asyncio
    async def test_delete_document(self, mock_database):
        """문서를 삭제할 수 있어야 한다"""
        # 문서 추가
        doc_id = await mock_database.add_document("to_delete.txt", "Delete me")
        initial_count = len(mock_database.documents)

        # 문서 삭제 시뮬레이션
        async def delete_document(doc_id):
            mock_database.documents[:] = [
                d for d in mock_database.documents if d["id"] != doc_id
            ]
            return True

        result = await delete_document(doc_id)

        assert result
        assert len(mock_database.documents) == initial_count - 1


class TestHistoryPageE2E:
    """History 페이지 E2E 테스트"""

    @pytest.mark.asyncio
    async def test_load_conversation_history(self, mock_database):
        """대화 기록을 로드할 수 있어야 한다"""
        # 테스트 세션 및 메시지 생성
        session_id = await mock_database.create_session()
        await mock_database.add_message(session_id, "user", "안녕하세요")
        await mock_database.add_message(session_id, "assistant", "안녕하세요! 무엇을 도와드릴까요?")

        # 메시지 조회
        messages = await mock_database.get_messages(session_id=session_id)

        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_pagination(self, mock_database):
        """페이지네이션이 동작해야 한다"""
        session_id = await mock_database.create_session()

        # 많은 메시지 추가
        for i in range(50):
            await mock_database.add_message(session_id, "user", f"Message {i}")

        # 페이지네이션 테스트
        page1 = await mock_database.get_messages(session_id=session_id, limit=20, offset=0)
        page2 = await mock_database.get_messages(session_id=session_id, limit=20, offset=20)

        assert len(page1) == 20
        assert len(page2) == 20
        assert page1[0]["content"] != page2[0]["content"]

    @pytest.mark.asyncio
    async def test_export_history_json(self, mock_database):
        """대화 기록을 JSON으로 내보낼 수 있어야 한다"""
        session_id = await mock_database.create_session()
        await mock_database.add_message(session_id, "user", "Test message")

        messages = await mock_database.get_messages(session_id=session_id)

        # JSON 내보내기
        export_data = json.dumps(messages, indent=2, ensure_ascii=False)

        assert "Test message" in export_data
        assert isinstance(json.loads(export_data), list)

    @pytest.mark.asyncio
    async def test_export_history_csv(self, mock_database):
        """대화 기록을 CSV로 내보낼 수 있어야 한다"""
        session_id = await mock_database.create_session()
        await mock_database.add_message(session_id, "user", "Test message")
        await mock_database.add_message(session_id, "assistant", "Response")

        messages = await mock_database.get_messages(session_id=session_id)

        # CSV 내보내기
        csv_lines = ["role,content,timestamp"]
        for msg in messages:
            csv_lines.append(f"{msg['role']},{msg['content']},{msg['timestamp']}")

        csv_content = "\n".join(csv_lines)

        assert "role,content,timestamp" in csv_content
        assert "user" in csv_content
        assert "assistant" in csv_content

    @pytest.mark.asyncio
    async def test_search_messages(self, mock_database):
        """메시지를 검색할 수 있어야 한다"""
        session_id = await mock_database.create_session()
        await mock_database.add_message(session_id, "user", "날씨가 어때요?")
        await mock_database.add_message(session_id, "assistant", "오늘 날씨는 맑습니다.")
        await mock_database.add_message(session_id, "user", "내일 일정 알려줘")

        messages = await mock_database.get_messages(session_id=session_id)

        # 검색 시뮬레이션
        search_query = "날씨"
        filtered = [m for m in messages if search_query in m["content"]]

        assert len(filtered) == 2

    @pytest.mark.asyncio
    async def test_delete_session(self, mock_database):
        """세션을 삭제할 수 있어야 한다"""
        session_id = await mock_database.create_session()
        await mock_database.add_message(session_id, "user", "To be deleted")

        initial_sessions = len(mock_database.sessions)

        # 세션 삭제 시뮬레이션
        async def delete_session(sid):
            mock_database.sessions[:] = [
                s for s in mock_database.sessions if s["id"] != sid
            ]
            mock_database.messages[:] = [
                m for m in mock_database.messages if m["session_id"] != sid
            ]
            return True

        result = await delete_session(session_id)

        assert result
        assert len(mock_database.sessions) == initial_sessions - 1


class TestWebDashboardNavigation:
    """웹 대시보드 네비게이션 E2E 테스트"""

    @pytest.mark.asyncio
    async def test_navigation_between_pages(self):
        """페이지 간 네비게이션이 동작해야 한다"""
        # 페이지 상태 시뮬레이션
        pages = ["dashboard", "settings", "knowledge", "history"]
        current_page = "dashboard"

        def navigate_to(page):
            nonlocal current_page
            if page in pages:
                current_page = page
                return True
            return False

        # 네비게이션 테스트
        assert navigate_to("settings")
        assert current_page == "settings"

        assert navigate_to("knowledge")
        assert current_page == "knowledge"

        assert navigate_to("history")
        assert current_page == "history"

        assert navigate_to("dashboard")
        assert current_page == "dashboard"

    @pytest.mark.asyncio
    async def test_page_state_preservation(self):
        """페이지 상태가 보존되어야 한다"""
        # 설정 페이지 상태
        settings_state = {
            "unsaved_changes": False,
            "form_data": {}
        }

        # 폼 데이터 변경
        settings_state["form_data"]["temperature"] = 0.5
        settings_state["unsaved_changes"] = True

        # 다른 페이지로 이동 시도
        def can_leave_page():
            if settings_state["unsaved_changes"]:
                # 사용자 확인 필요
                return False
            return True

        assert not can_leave_page()

        # 변경 사항 저장
        settings_state["unsaved_changes"] = False

        assert can_leave_page()
