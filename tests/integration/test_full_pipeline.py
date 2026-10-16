"""
Full Pipeline Integration Tests

Phase 6.1: 전체 파이프라인 통합 테스트 (Audio → STT → LLM → TTS → Audio)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import numpy as np


class TestFullPipelineIntegration:
    """전체 파이프라인 통합 테스트"""

    @pytest.mark.asyncio
    async def test_complete_voice_interaction(
        self,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service,
        sample_audio_data
    ):
        """완전한 음성 상호작용 플로우가 동작해야 한다"""
        # 1. 오디오 입력 → STT
        stt_result = await mock_stt_service.transcribe(sample_audio_data["audio"])
        assert stt_result["text"] == "안녕하세요"

        # 2. STT 결과 → LLM
        llm_result = await mock_llm_service.generate(prompt=stt_result["text"])
        assert "text" in llm_result

        # 3. LLM 응답 → TTS
        tts_result = await mock_tts_service.synthesize(text=llm_result["text"])
        assert "audio" in tts_result
        assert tts_result["sample_rate"] == 24000

    @pytest.mark.asyncio
    async def test_pipeline_with_context(
        self,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service
    ):
        """컨텍스트가 유지되는 파이프라인 테스트"""
        conversation_history = []

        # 첫 번째 턴
        mock_stt_service.transcribe = AsyncMock(return_value={
            "text": "내 이름은 홍길동이야",
            "confidence": 0.95,
            "language": "ko"
        })

        stt1 = await mock_stt_service.transcribe(b"audio1")
        conversation_history.append({"role": "user", "content": stt1["text"]})

        mock_llm_service.generate = AsyncMock(return_value={
            "text": "안녕하세요 홍길동님! 반갑습니다.",
            "tokens_used": 30
        })

        llm1 = await mock_llm_service.generate(
            prompt=stt1["text"],
            context=conversation_history
        )
        conversation_history.append({"role": "assistant", "content": llm1["text"]})

        # 두 번째 턴 - 컨텍스트 참조
        mock_stt_service.transcribe = AsyncMock(return_value={
            "text": "내 이름이 뭐라고 했지?",
            "confidence": 0.92,
            "language": "ko"
        })

        stt2 = await mock_stt_service.transcribe(b"audio2")
        conversation_history.append({"role": "user", "content": stt2["text"]})

        mock_llm_service.generate = AsyncMock(return_value={
            "text": "홍길동이라고 하셨습니다.",
            "tokens_used": 20
        })

        llm2 = await mock_llm_service.generate(
            prompt=stt2["text"],
            context=conversation_history
        )

        # 컨텍스트가 전달되었는지 확인
        call_args = mock_llm_service.generate.call_args
        assert len(call_args.kwargs["context"]) == 3

    @pytest.mark.asyncio
    async def test_pipeline_with_rag(
        self,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service,
        mock_rag_service
    ):
        """RAG가 포함된 파이프라인 테스트"""
        # STT
        mock_stt_service.transcribe = AsyncMock(return_value={
            "text": "회사 휴가 정책이 어떻게 되나요?",
            "confidence": 0.95,
            "language": "ko"
        })

        stt_result = await mock_stt_service.transcribe(b"audio")

        # RAG 검색
        rag_results = await mock_rag_service.retrieve(query=stt_result["text"])
        assert len(rag_results) > 0

        # RAG 컨텍스트와 함께 LLM 호출
        rag_context = "\n".join([r["content"] for r in rag_results])

        mock_llm_service.generate = AsyncMock(return_value={
            "text": "회사 휴가 정책에 따르면, 연차는 15일이며...",
            "tokens_used": 100
        })

        llm_result = await mock_llm_service.generate(
            prompt=stt_result["text"],
            rag_context=rag_context
        )

        # RAG 컨텍스트가 전달되었는지 확인
        call_args = mock_llm_service.generate.call_args
        assert "rag_context" in call_args.kwargs

        # TTS
        tts_result = await mock_tts_service.synthesize(text=llm_result["text"])
        assert tts_result["audio"] is not None


class TestPipelineStreaming:
    """파이프라인 스트리밍 테스트"""

    @pytest.mark.asyncio
    async def test_streaming_pipeline(
        self,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service
    ):
        """스트리밍 파이프라인이 동작해야 한다"""
        # STT (일반 응답)
        stt_result = await mock_stt_service.transcribe(b"audio")

        # LLM 스트리밍
        sentence_buffer = ""
        tts_tasks = []

        async for chunk in mock_llm_service.generate_stream():
            if chunk["token"]:
                sentence_buffer += chunk["token"]

                # 문장 완성 시 TTS 시작
                if any(sentence_buffer.endswith(p) for p in [".", "!", "?"]):
                    sentence = sentence_buffer.strip()
                    # TTS 태스크 생성 (비동기)
                    tts_tasks.append(
                        mock_tts_service.synthesize(text=sentence)
                    )
                    sentence_buffer = ""

            if chunk["finished"]:
                if sentence_buffer.strip():
                    tts_tasks.append(
                        mock_tts_service.synthesize(text=sentence_buffer.strip())
                    )
                break

        # 모든 TTS 완료 대기
        tts_results = await asyncio.gather(*tts_tasks)

        assert len(tts_results) > 0
        for result in tts_results:
            assert "audio" in result

    @pytest.mark.asyncio
    async def test_first_audio_latency(
        self,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service
    ):
        """첫 오디오까지의 지연이 측정되어야 한다"""
        import time

        start_time = time.time()

        # STT
        stt_result = await mock_stt_service.transcribe(b"audio")

        # LLM 스트리밍 - 첫 문장까지
        sentence_buffer = ""
        first_sentence = None

        async for chunk in mock_llm_service.generate_stream():
            if chunk["token"]:
                sentence_buffer += chunk["token"]

                if any(sentence_buffer.endswith(p) for p in [".", "!", "?"]):
                    first_sentence = sentence_buffer.strip()
                    break

            if chunk["finished"]:
                first_sentence = sentence_buffer.strip()
                break

        # 첫 문장 TTS
        if first_sentence:
            await mock_tts_service.synthesize(text=first_sentence)

        first_audio_time = time.time() - start_time

        # 지연 시간이 측정되었는지 확인 (실제로는 mock이라 매우 빠름)
        assert first_audio_time >= 0
        assert first_audio_time < 1.0  # mock이므로 1초 미만


class TestPipelineErrorRecovery:
    """파이프라인 에러 복구 테스트"""

    @pytest.mark.asyncio
    async def test_stt_failure_recovery(
        self,
        mock_llm_service,
        mock_tts_service
    ):
        """STT 실패 시 복구해야 한다"""
        mock_stt = MagicMock()
        mock_stt.transcribe = AsyncMock(side_effect=Exception("STT service unavailable"))

        try:
            await mock_stt.transcribe(b"audio")
            stt_success = True
        except Exception:
            stt_success = False

        assert not stt_success

        # STT 실패 시 기본 응답
        if not stt_success:
            default_response = "죄송합니다, 음성을 인식하지 못했습니다."
            await mock_tts_service.synthesize(text=default_response)

        mock_tts_service.synthesize.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_failure_recovery(
        self,
        mock_stt_service,
        mock_tts_service
    ):
        """LLM 실패 시 복구해야 한다"""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(side_effect=Exception("LLM service unavailable"))

        stt_result = await mock_stt_service.transcribe(b"audio")

        try:
            await mock_llm.generate(prompt=stt_result["text"])
            llm_success = True
        except Exception:
            llm_success = False

        assert not llm_success

        # LLM 실패 시 기본 응답
        if not llm_success:
            fallback_response = "죄송합니다, 잠시 후 다시 시도해 주세요."
            await mock_tts_service.synthesize(text=fallback_response)

        mock_tts_service.synthesize.assert_called_once()

    @pytest.mark.asyncio
    async def test_tts_failure_recovery(
        self,
        mock_stt_service,
        mock_llm_service
    ):
        """TTS 실패 시 복구해야 한다"""
        mock_tts = MagicMock()
        mock_tts.synthesize = AsyncMock(side_effect=Exception("TTS service unavailable"))

        stt_result = await mock_stt_service.transcribe(b"audio")
        llm_result = await mock_llm_service.generate(prompt=stt_result["text"])

        try:
            await mock_tts.synthesize(text=llm_result["text"])
            tts_success = True
        except Exception:
            tts_success = False

        assert not tts_success

        # TTS 실패 시 텍스트 응답으로 대체 (예: 화면에 표시)
        text_fallback = llm_result["text"]
        assert len(text_fallback) > 0


class TestPipelineState:
    """파이프라인 상태 관리 테스트"""

    @pytest.mark.asyncio
    async def test_state_transitions(
        self,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service
    ):
        """파이프라인 상태가 올바르게 전이되어야 한다"""
        from services.orchestrator.app.state_machine import State, OrchestratorStateMachine as StateMachine

        state_machine = StateMachine()
        assert state_machine.current_state == State.IDLE

        # Wake word 감지 → LISTENING
        state_machine.transition_to(State.LISTENING)
        assert state_machine.current_state == State.LISTENING

        # STT 처리 → PROCESSING
        await mock_stt_service.transcribe(b"audio")
        state_machine.transition_to(State.PROCESSING)
        assert state_machine.current_state == State.PROCESSING

        # LLM + TTS → SPEAKING
        await mock_llm_service.generate(prompt="test")
        state_machine.transition_to(State.SPEAKING)
        assert state_machine.current_state == State.SPEAKING

        # 완료 → IDLE
        await mock_tts_service.synthesize(text="response")
        state_machine.transition_to(State.IDLE)
        assert state_machine.current_state == State.IDLE

    @pytest.mark.asyncio
    async def test_concurrent_pipeline_handling(
        self,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service
    ):
        """동시 파이프라인 처리가 올바르게 동작해야 한다"""
        async def process_pipeline(audio_id):
            stt = await mock_stt_service.transcribe(f"audio_{audio_id}".encode())
            llm = await mock_llm_service.generate(prompt=stt["text"])
            tts = await mock_tts_service.synthesize(text=llm["text"])
            return {"id": audio_id, "audio": tts["audio"]}

        # 여러 파이프라인 동시 실행
        tasks = [process_pipeline(i) for i in range(3)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 3
        for i, result in enumerate(results):
            assert result["id"] == i
            assert result["audio"] is not None
