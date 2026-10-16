"""
STT to LLM Integration Tests

Phase 6.1: STT → LLM 통합 테스트
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio


class TestSTTToLLMIntegration:
    """STT에서 LLM으로의 데이터 흐름 테스트"""

    @pytest.mark.asyncio
    async def test_stt_result_flows_to_llm(self, mock_stt_service, mock_llm_service):
        """STT 결과가 LLM으로 전달되어야 한다"""
        # STT로 음성을 텍스트로 변환
        stt_result = await mock_stt_service.transcribe(b"fake_audio_data")

        assert stt_result["text"] == "안녕하세요"
        assert stt_result["confidence"] > 0.9

        # STT 결과를 LLM에 전달
        llm_result = await mock_llm_service.generate(
            prompt=stt_result["text"],
            system_prompt="You are a helpful assistant."
        )

        assert "text" in llm_result
        assert len(llm_result["text"]) > 0

    @pytest.mark.asyncio
    async def test_stt_confidence_threshold(self, mock_stt_service, mock_llm_service):
        """STT 신뢰도가 임계값 미만이면 LLM 호출하지 않아야 한다"""
        # 낮은 신뢰도의 STT 결과 시뮬레이션
        mock_stt_service.transcribe = AsyncMock(return_value={
            "text": "불명확한 텍스트",
            "confidence": 0.3,
            "language": "ko"
        })

        stt_result = await mock_stt_service.transcribe(b"noisy_audio")

        confidence_threshold = 0.5
        llm_called = False

        if stt_result["confidence"] >= confidence_threshold:
            await mock_llm_service.generate(prompt=stt_result["text"])
            llm_called = True

        assert not llm_called
        mock_llm_service.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_stt_empty_result_handling(self, mock_stt_service, mock_llm_service):
        """STT 결과가 빈 경우 LLM 호출하지 않아야 한다"""
        mock_stt_service.transcribe = AsyncMock(return_value={
            "text": "",
            "confidence": 0.0,
            "language": "ko"
        })

        stt_result = await mock_stt_service.transcribe(b"silence_audio")

        if stt_result["text"].strip():
            await mock_llm_service.generate(prompt=stt_result["text"])

        mock_llm_service.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_conversation_context_accumulation(self, mock_stt_service, mock_llm_service):
        """대화 컨텍스트가 누적되어야 한다"""
        conversation_history = []

        # 첫 번째 대화
        mock_stt_service.transcribe = AsyncMock(return_value={
            "text": "오늘 날씨 어때?",
            "confidence": 0.95,
            "language": "ko"
        })

        stt_result1 = await mock_stt_service.transcribe(b"audio1")
        conversation_history.append({"role": "user", "content": stt_result1["text"]})

        mock_llm_service.generate = AsyncMock(return_value={
            "text": "오늘 날씨가 좋습니다.",
            "tokens_used": 30
        })

        llm_result1 = await mock_llm_service.generate(
            prompt=stt_result1["text"],
            context=conversation_history
        )
        conversation_history.append({"role": "assistant", "content": llm_result1["text"]})

        # 두 번째 대화
        mock_stt_service.transcribe = AsyncMock(return_value={
            "text": "비 올 것 같아?",
            "confidence": 0.92,
            "language": "ko"
        })

        stt_result2 = await mock_stt_service.transcribe(b"audio2")
        conversation_history.append({"role": "user", "content": stt_result2["text"]})

        # 컨텍스트 누적 확인
        assert len(conversation_history) == 3
        assert conversation_history[0]["role"] == "user"
        assert conversation_history[1]["role"] == "assistant"
        assert conversation_history[2]["role"] == "user"

    @pytest.mark.asyncio
    async def test_stt_language_detection_passed_to_llm(self, mock_stt_service, mock_llm_service):
        """STT에서 감지된 언어가 LLM에 전달되어야 한다"""
        mock_stt_service.transcribe = AsyncMock(return_value={
            "text": "Hello, how are you?",
            "confidence": 0.98,
            "language": "en"
        })

        stt_result = await mock_stt_service.transcribe(b"english_audio")

        # 언어에 따른 시스템 프롬프트 조정
        system_prompts = {
            "ko": "당신은 친절한 한국어 어시스턴트입니다.",
            "en": "You are a helpful English assistant."
        }

        system_prompt = system_prompts.get(stt_result["language"], system_prompts["en"])

        await mock_llm_service.generate(
            prompt=stt_result["text"],
            system_prompt=system_prompt
        )

        # LLM이 호출되었는지 확인
        mock_llm_service.generate.assert_called_once()
        call_args = mock_llm_service.generate.call_args
        assert call_args.kwargs["system_prompt"] == "You are a helpful English assistant."


class TestSTTToLLMErrorHandling:
    """STT-LLM 통합 에러 처리 테스트"""

    @pytest.mark.asyncio
    async def test_stt_timeout_handling(self, mock_llm_service):
        """STT 타임아웃 시 적절히 처리해야 한다"""
        async def slow_transcribe(*args, **kwargs):
            await asyncio.sleep(10)
            return {"text": "delayed", "confidence": 0.9, "language": "ko"}

        mock_stt = MagicMock()
        mock_stt.transcribe = slow_transcribe

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                mock_stt.transcribe(b"audio"),
                timeout=0.1
            )

        # LLM은 호출되지 않아야 함
        mock_llm_service.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_error_does_not_affect_stt(self, mock_stt_service):
        """LLM 에러가 STT에 영향을 주지 않아야 한다"""
        # STT는 정상 동작
        stt_result = await mock_stt_service.transcribe(b"audio")
        assert stt_result["text"] == "안녕하세요"

        # LLM 에러 시뮬레이션
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(side_effect=Exception("LLM service unavailable"))

        with pytest.raises(Exception, match="LLM service unavailable"):
            await mock_llm.generate(prompt=stt_result["text"])

        # STT 결과는 여전히 유효
        assert stt_result["confidence"] > 0.9

    @pytest.mark.asyncio
    async def test_retry_on_transient_failure(self, mock_stt_service, mock_llm_service):
        """일시적 실패 시 재시도해야 한다"""
        call_count = 0

        async def flaky_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Transient error")
            return {"text": "성공!", "tokens_used": 10}

        mock_llm_service.generate = flaky_generate

        stt_result = await mock_stt_service.transcribe(b"audio")

        # 재시도 로직
        max_retries = 3
        result = None
        for attempt in range(max_retries):
            try:
                result = await mock_llm_service.generate(prompt=stt_result["text"])
                break
            except Exception:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(0.01)

        assert result is not None
        assert result["text"] == "성공!"
        assert call_count == 3


class TestSTTToLLMStreaming:
    """STT-LLM 스트리밍 통합 테스트"""

    @pytest.mark.asyncio
    async def test_stt_stream_to_llm(self, mock_llm_service):
        """STT 스트리밍 결과가 LLM으로 전달되어야 한다"""
        # STT 스트리밍 결과 시뮬레이션
        stt_chunks = ["안녕", "하세요", " 반갑", "습니다"]
        accumulated_text = ""

        for chunk in stt_chunks:
            accumulated_text += chunk

        # 최종 텍스트로 LLM 호출
        await mock_llm_service.generate(prompt=accumulated_text)

        mock_llm_service.generate.assert_called_once()
        call_args = mock_llm_service.generate.call_args
        assert call_args.kwargs["prompt"] == "안녕하세요 반갑습니다"

    @pytest.mark.asyncio
    async def test_llm_streaming_response(self, mock_stt_service, mock_llm_service):
        """LLM 스트리밍 응답을 처리할 수 있어야 한다"""
        stt_result = await mock_stt_service.transcribe(b"audio")

        # LLM 스트리밍 응답 수집
        response_tokens = []
        async for chunk in mock_llm_service.generate_stream():
            if chunk["token"]:
                response_tokens.append(chunk["token"])
            if chunk["finished"]:
                break

        full_response = "".join(response_tokens)
        assert len(full_response) > 0
        assert "안녕" in full_response
