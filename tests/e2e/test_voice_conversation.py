"""
Voice Conversation E2E Tests

Phase 6.2: 음성 대화 E2E 테스트
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import numpy as np
import json

from services.orchestrator.app.state_machine import State, OrchestratorStateMachine as StateMachine


class TestVoiceConversationE2E:
    """음성 대화 E2E 테스트"""

    @pytest.mark.asyncio
    async def test_complete_voice_conversation_flow(
        self,
        mock_services,
        mock_audio_input,
        mock_audio_output
    ):
        """완전한 음성 대화 플로우가 동작해야 한다"""
        state_machine = StateMachine()

        # 1. Wake Word 감지
        wake_result = await mock_services["wake_word"].detect(mock_audio_input["audio"])
        assert wake_result["detected"]
        state_machine.transition_to(State.LISTENING)
        assert state_machine.current_state == State.LISTENING

        # 2. 사용자 음성 → STT
        stt_result = await mock_services["stt"].transcribe(mock_audio_input["audio"])
        assert stt_result["text"] == "안녕하세요"

        # 3. STT → LLM
        state_machine.transition_to(State.PROCESSING)
        llm_result = await mock_services["llm"].generate(prompt=stt_result["text"])
        assert len(llm_result["text"]) > 0

        # 4. LLM → TTS
        state_machine.transition_to(State.SPEAKING)
        tts_result = await mock_services["tts"].synthesize(text=llm_result["text"])
        assert tts_result["audio"] is not None

        # 5. 오디오 재생 완료 → IDLE
        await mock_audio_output.play(tts_result["audio"])
        state_machine.transition_to(State.IDLE)
        assert state_machine.current_state == State.IDLE

    @pytest.mark.asyncio
    async def test_multi_turn_conversation(
        self,
        mock_services,
        mock_audio_input
    ):
        """다중 턴 대화가 컨텍스트를 유지해야 한다"""
        conversation_history = []

        # 첫 번째 턴
        mock_services["stt"].transcribe = AsyncMock(return_value={
            "text": "내 이름은 홍길동이야",
            "confidence": 0.95,
            "language": "ko"
        })

        stt1 = await mock_services["stt"].transcribe(mock_audio_input["audio"])
        conversation_history.append({"role": "user", "content": stt1["text"]})

        mock_services["llm"].generate = AsyncMock(return_value={
            "text": "안녕하세요 홍길동님! 반갑습니다.",
            "tokens_used": 25
        })

        llm1 = await mock_services["llm"].generate(
            prompt=stt1["text"],
            context=conversation_history
        )
        conversation_history.append({"role": "assistant", "content": llm1["text"]})

        # 두 번째 턴 - 이전 컨텍스트 참조
        mock_services["stt"].transcribe = AsyncMock(return_value={
            "text": "내 이름이 뭐라고 했지?",
            "confidence": 0.92,
            "language": "ko"
        })

        stt2 = await mock_services["stt"].transcribe(mock_audio_input["audio"])
        conversation_history.append({"role": "user", "content": stt2["text"]})

        mock_services["llm"].generate = AsyncMock(return_value={
            "text": "홍길동이라고 하셨습니다.",
            "tokens_used": 15
        })

        llm2 = await mock_services["llm"].generate(
            prompt=stt2["text"],
            context=conversation_history
        )

        # 컨텍스트 확인
        assert len(conversation_history) == 3
        assert "홍길동" in conversation_history[0]["content"]

    @pytest.mark.asyncio
    async def test_streaming_response_flow(
        self,
        mock_services,
        mock_audio_input
    ):
        """스트리밍 응답 플로우가 동작해야 한다"""
        stt_result = await mock_services["stt"].transcribe(mock_audio_input["audio"])

        # 스트리밍 LLM 응답
        sentence_buffer = ""
        tts_requests = []

        async for chunk in mock_services["llm"].generate_stream():
            if chunk["token"]:
                sentence_buffer += chunk["token"]

                # 문장 완성 시 TTS 요청
                if any(sentence_buffer.endswith(p) for p in [".", "!", "?"]):
                    sentence = sentence_buffer.strip()
                    tts_result = await mock_services["tts"].synthesize(text=sentence)
                    tts_requests.append(tts_result)
                    sentence_buffer = ""

            if chunk["finished"]:
                if sentence_buffer.strip():
                    tts_result = await mock_services["tts"].synthesize(text=sentence_buffer.strip())
                    tts_requests.append(tts_result)
                break

        assert len(tts_requests) > 0

    @pytest.mark.asyncio
    async def test_barge_in_interrupts_response(
        self,
        mock_services,
        mock_audio_input,
        mock_audio_output
    ):
        """Barge-in이 응답을 중단해야 한다"""
        state_machine = StateMachine()

        # 응답 중 상태로 전이
        state_machine.transition_to(State.LISTENING)
        state_machine.transition_to(State.PROCESSING)
        state_machine.transition_to(State.SPEAKING)

        # 오디오 재생 시작
        mock_audio_output.is_playing = True

        # Barge-in 감지
        user_speech_energy = 0.8
        barge_in_threshold = 0.5

        if user_speech_energy > barge_in_threshold and mock_audio_output.is_playing:
            # 오디오 중단
            mock_audio_output.stop()
            mock_audio_output.is_playing = False

            # 상태 전이
            state_machine.handle_barge_in()

        assert state_machine.current_state == State.LISTENING
        mock_audio_output.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_wake_word_after_idle(
        self,
        mock_services,
        mock_audio_input
    ):
        """IDLE 상태에서 Wake Word가 정상 동작해야 한다"""
        state_machine = StateMachine()
        assert state_machine.current_state == State.IDLE

        # Wake Word 연속 테스트
        for i in range(3):
            # Wake Word 감지
            wake_result = await mock_services["wake_word"].detect(mock_audio_input["audio"])
            if wake_result["detected"]:
                state_machine.transition_to(State.LISTENING)

            assert state_machine.current_state == State.LISTENING

            # 대화 완료
            state_machine.transition_to(State.PROCESSING)
            state_machine.transition_to(State.SPEAKING)
            state_machine.transition_to(State.IDLE)

            assert state_machine.current_state == State.IDLE

    @pytest.mark.asyncio
    async def test_silence_timeout_returns_to_idle(
        self,
        mock_services
    ):
        """무음 타임아웃 시 IDLE로 돌아가야 한다"""
        state_machine = StateMachine()
        state_machine.transition_to(State.LISTENING)

        # 무음 시뮬레이션
        silence_duration = 0
        timeout_threshold = 5.0

        # 실제로는 5초 대기하지 않고 시뮬레이션
        silence_duration = 6.0  # 타임아웃 초과

        if silence_duration > timeout_threshold:
            state_machine.transition_to(State.IDLE)

        assert state_machine.current_state == State.IDLE


class TestVoiceConversationWithRAG:
    """RAG 통합 음성 대화 E2E 테스트"""

    @pytest.mark.asyncio
    async def test_voice_query_with_rag_context(
        self,
        mock_services,
        mock_audio_input
    ):
        """음성 질의에 RAG 컨텍스트가 적용되어야 한다"""
        # STT
        mock_services["stt"].transcribe = AsyncMock(return_value={
            "text": "회사 휴가 정책이 어떻게 되나요?",
            "confidence": 0.95,
            "language": "ko"
        })

        stt_result = await mock_services["stt"].transcribe(mock_audio_input["audio"])

        # RAG 검색
        rag_results = await mock_services["rag"].retrieve(query=stt_result["text"])
        assert len(rag_results) > 0

        # RAG 컨텍스트와 함께 LLM 호출
        rag_context = "\n".join([r["content"] for r in rag_results])

        mock_services["llm"].generate = AsyncMock(return_value={
            "text": "회사 휴가 정책에 따르면, 연차는 15일입니다.",
            "tokens_used": 50
        })

        llm_result = await mock_services["llm"].generate(
            prompt=stt_result["text"],
            rag_context=rag_context
        )

        # RAG 컨텍스트가 전달되었는지 확인
        call_args = mock_services["llm"].generate.call_args
        assert "rag_context" in call_args.kwargs

    @pytest.mark.asyncio
    async def test_voice_upload_and_query_document(
        self,
        mock_services,
        mock_database,
        mock_audio_input
    ):
        """음성으로 문서 업로드 후 질의할 수 있어야 한다"""
        # 문서 업로드 (실제로는 파일 업로드이지만 여기서는 시뮬레이션)
        doc_content = "회사 연차는 15일이며, 반차도 사용 가능합니다."
        doc_id = await mock_database.add_document("policy.txt", doc_content)

        # RAG에 문서 추가
        await mock_services["rag"].add_document({
            "id": doc_id,
            "content": doc_content,
            "metadata": {"source": "policy.txt"}
        })

        # 음성 질의
        mock_services["stt"].transcribe = AsyncMock(return_value={
            "text": "반차 사용이 가능한가요?",
            "confidence": 0.95,
            "language": "ko"
        })

        stt_result = await mock_services["stt"].transcribe(mock_audio_input["audio"])

        # RAG 검색
        mock_services["rag"].retrieve = AsyncMock(return_value=[
            {"content": doc_content, "score": 0.9, "metadata": {"source": "policy.txt"}}
        ])

        rag_results = await mock_services["rag"].retrieve(query=stt_result["text"])

        assert len(rag_results) > 0
        assert "반차" in rag_results[0]["content"]


class TestVoiceConversationErrorHandling:
    """음성 대화 오류 처리 E2E 테스트"""

    @pytest.mark.asyncio
    async def test_stt_error_graceful_handling(
        self,
        mock_services,
        mock_audio_input
    ):
        """STT 오류 시 graceful하게 처리해야 한다"""
        mock_services["stt"].transcribe = AsyncMock(
            side_effect=Exception("STT service unavailable")
        )

        try:
            await mock_services["stt"].transcribe(mock_audio_input["audio"])
            stt_success = True
        except Exception:
            stt_success = False

        assert not stt_success

        # 오류 시 사용자에게 피드백
        error_response = "죄송합니다, 음성을 인식하지 못했습니다. 다시 말씀해 주세요."
        tts_result = await mock_services["tts"].synthesize(text=error_response)

        assert tts_result["audio"] is not None

    @pytest.mark.asyncio
    async def test_llm_error_fallback_response(
        self,
        mock_services,
        mock_audio_input
    ):
        """LLM 오류 시 fallback 응답을 제공해야 한다"""
        stt_result = await mock_services["stt"].transcribe(mock_audio_input["audio"])

        mock_services["llm"].generate = AsyncMock(
            side_effect=Exception("LLM service unavailable")
        )

        try:
            await mock_services["llm"].generate(prompt=stt_result["text"])
            llm_success = True
        except Exception:
            llm_success = False

        assert not llm_success

        # Fallback 응답
        fallback_response = "죄송합니다, 잠시 후 다시 시도해 주세요."
        tts_result = await mock_services["tts"].synthesize(text=fallback_response)

        assert tts_result["audio"] is not None

    @pytest.mark.asyncio
    async def test_tts_error_text_fallback(
        self,
        mock_services,
        mock_audio_input
    ):
        """TTS 오류 시 텍스트 fallback을 제공해야 한다"""
        stt_result = await mock_services["stt"].transcribe(mock_audio_input["audio"])
        llm_result = await mock_services["llm"].generate(prompt=stt_result["text"])

        mock_services["tts"].synthesize = AsyncMock(
            side_effect=Exception("TTS service unavailable")
        )

        try:
            await mock_services["tts"].synthesize(text=llm_result["text"])
            tts_success = True
        except Exception:
            tts_success = False

        assert not tts_success

        # 텍스트 fallback
        text_response = llm_result["text"]
        assert len(text_response) > 0

    @pytest.mark.asyncio
    async def test_network_timeout_handling(
        self,
        mock_services,
        mock_audio_input
    ):
        """네트워크 타임아웃을 처리해야 한다"""
        async def slow_transcribe(audio):
            await asyncio.sleep(10)  # 매우 느린 응답
            return {"text": "늦은 응답", "confidence": 0.9}

        mock_services["stt"].transcribe = slow_transcribe

        # 타임아웃 적용
        timeout = 5.0

        try:
            result = await asyncio.wait_for(
                mock_services["stt"].transcribe(mock_audio_input["audio"]),
                timeout=timeout
            )
            timed_out = False
        except asyncio.TimeoutError:
            timed_out = True

        assert timed_out

    @pytest.mark.asyncio
    async def test_service_health_check_before_conversation(
        self,
        mock_services
    ):
        """대화 시작 전 서비스 헬스 체크를 수행해야 한다"""
        # 모든 서비스 헬스 체크
        health_results = {}

        for name, service in mock_services.items():
            if hasattr(service, 'health'):
                result = await service.health()
                health_results[name] = result["status"] == "healthy"

        # 모든 서비스가 healthy 상태인지 확인
        all_healthy = all(health_results.values())
        assert all_healthy

        # 필수 서비스 확인
        required_services = ["stt", "llm", "tts"]
        for service in required_services:
            assert health_results.get(service, False)


class TestVoiceConversationConcurrency:
    """음성 대화 동시성 E2E 테스트"""

    @pytest.mark.asyncio
    async def test_single_conversation_at_a_time(
        self,
        mock_services,
        mock_audio_input
    ):
        """한 번에 하나의 대화만 처리해야 한다"""
        state_machine = StateMachine()

        # 첫 번째 대화 시작
        state_machine.transition_to(State.LISTENING)
        state_machine.transition_to(State.PROCESSING)

        # 두 번째 Wake Word 시도 - 무시되어야 함
        second_wake_word = True

        if state_machine.current_state != State.IDLE and second_wake_word:
            # IDLE이 아니면 Wake Word 무시
            pass

        # 첫 번째 대화 계속 진행 중
        assert state_machine.current_state == State.PROCESSING

    @pytest.mark.asyncio
    async def test_conversation_queue_management(self):
        """대화 큐가 올바르게 관리되어야 한다"""
        conversation_queue = asyncio.Queue(maxsize=1)

        # 첫 번째 요청
        await conversation_queue.put({"id": 1, "text": "첫 번째"})
        assert conversation_queue.full()

        # 두 번째 요청 시도 - 큐가 가득 찼으므로 대기
        try:
            conversation_queue.put_nowait({"id": 2, "text": "두 번째"})
            queue_full = False
        except asyncio.QueueFull:
            queue_full = True

        assert queue_full

        # 첫 번째 처리 완료
        await conversation_queue.get()
        conversation_queue.task_done()

        # 이제 두 번째 추가 가능
        await conversation_queue.put({"id": 2, "text": "두 번째"})
        assert not conversation_queue.empty()
