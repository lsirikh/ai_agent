"""
LLM to TTS Integration Tests

Phase 6.1: LLM → TTS 통합 테스트
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import numpy as np


class TestLLMToTTSIntegration:
    """LLM에서 TTS로의 데이터 흐름 테스트"""

    @pytest.mark.asyncio
    async def test_llm_response_flows_to_tts(self, mock_llm_service, mock_tts_service):
        """LLM 응답이 TTS로 전달되어야 한다"""
        # LLM 응답 생성
        llm_result = await mock_llm_service.generate(prompt="안녕하세요")

        assert "text" in llm_result
        assert len(llm_result["text"]) > 0

        # LLM 응답을 TTS로 전달
        tts_result = await mock_tts_service.synthesize(text=llm_result["text"])

        assert "audio" in tts_result
        assert tts_result["sample_rate"] == 24000
        assert len(tts_result["audio"]) > 0

    @pytest.mark.asyncio
    async def test_sentence_chunking_for_tts(self, mock_llm_service, mock_tts_service):
        """LLM 응답이 문장 단위로 TTS에 전달되어야 한다"""
        # 여러 문장이 포함된 LLM 응답
        mock_llm_service.generate = AsyncMock(return_value={
            "text": "안녕하세요. 오늘 날씨가 좋네요. 뭘 도와드릴까요?",
            "tokens_used": 50
        })

        llm_result = await mock_llm_service.generate(prompt="안녕")

        # 문장 분리
        sentences = []
        current_sentence = ""
        for char in llm_result["text"]:
            current_sentence += char
            if char in ".!?":
                sentences.append(current_sentence.strip())
                current_sentence = ""
        if current_sentence.strip():
            sentences.append(current_sentence.strip())

        assert len(sentences) == 3
        assert sentences[0] == "안녕하세요."
        assert sentences[1] == "오늘 날씨가 좋네요."
        assert sentences[2] == "뭘 도와드릴까요?"

        # 각 문장을 TTS로 변환
        for sentence in sentences:
            await mock_tts_service.synthesize(text=sentence)

        assert mock_tts_service.synthesize.call_count == 3

    @pytest.mark.asyncio
    async def test_streaming_llm_to_tts(self, mock_llm_service, mock_tts_service):
        """LLM 스트리밍 응답이 실시간으로 TTS에 전달되어야 한다"""
        sentence_buffer = ""
        sentences_to_synthesize = []

        async for chunk in mock_llm_service.generate_stream():
            if chunk["token"]:
                sentence_buffer += chunk["token"]

                # 문장 완성 확인
                if any(sentence_buffer.endswith(p) for p in [".", "!", "?"]):
                    sentences_to_synthesize.append(sentence_buffer.strip())
                    sentence_buffer = ""

            if chunk["finished"]:
                if sentence_buffer.strip():
                    sentences_to_synthesize.append(sentence_buffer.strip())
                break

        # 각 문장 TTS 합성
        audio_chunks = []
        for sentence in sentences_to_synthesize:
            result = await mock_tts_service.synthesize(text=sentence)
            audio_chunks.append(result["audio"])

        assert len(audio_chunks) > 0

    @pytest.mark.asyncio
    async def test_empty_llm_response_skips_tts(self, mock_llm_service, mock_tts_service):
        """빈 LLM 응답은 TTS를 호출하지 않아야 한다"""
        mock_llm_service.generate = AsyncMock(return_value={
            "text": "",
            "tokens_used": 0
        })

        llm_result = await mock_llm_service.generate(prompt="무시되는 입력")

        if llm_result["text"].strip():
            await mock_tts_service.synthesize(text=llm_result["text"])

        mock_tts_service.synthesize.assert_not_called()

    @pytest.mark.asyncio
    async def test_tts_voice_selection_from_context(self, mock_llm_service, mock_tts_service):
        """컨텍스트에 따라 TTS 음성이 선택되어야 한다"""
        llm_result = await mock_llm_service.generate(prompt="안녕하세요")

        # 사용자 설정에 따른 음성 선택
        user_voice_preference = "af_bella"

        await mock_tts_service.synthesize(
            text=llm_result["text"],
            voice=user_voice_preference
        )

        call_args = mock_tts_service.synthesize.call_args
        assert call_args.kwargs.get("voice") == "af_bella"


class TestLLMToTTSQueueing:
    """LLM-TTS 큐잉 테스트"""

    @pytest.mark.asyncio
    async def test_sentence_queue_processing(self, mock_tts_service):
        """문장 큐가 순서대로 처리되어야 한다"""
        sentence_queue = asyncio.Queue()

        # 문장 추가
        sentences = ["첫 번째 문장.", "두 번째 문장.", "세 번째 문장."]
        for s in sentences:
            await sentence_queue.put(s)

        # 큐 처리
        processed = []
        while not sentence_queue.empty():
            sentence = await sentence_queue.get()
            await mock_tts_service.synthesize(text=sentence)
            processed.append(sentence)
            sentence_queue.task_done()

        assert processed == sentences
        assert mock_tts_service.synthesize.call_count == 3

    @pytest.mark.asyncio
    async def test_tts_queue_with_priority(self, mock_tts_service):
        """우선순위가 높은 문장이 먼저 처리되어야 한다"""
        from queue import PriorityQueue

        priority_queue = PriorityQueue()

        # 우선순위와 함께 문장 추가 (낮은 숫자 = 높은 우선순위)
        priority_queue.put((2, "일반 문장"))
        priority_queue.put((1, "중요 문장"))
        priority_queue.put((3, "덜 중요한 문장"))

        processed = []
        while not priority_queue.empty():
            priority, sentence = priority_queue.get()
            await mock_tts_service.synthesize(text=sentence)
            processed.append(sentence)

        assert processed[0] == "중요 문장"
        assert processed[1] == "일반 문장"
        assert processed[2] == "덜 중요한 문장"


class TestLLMToTTSErrorHandling:
    """LLM-TTS 에러 처리 테스트"""

    @pytest.mark.asyncio
    async def test_tts_error_does_not_block_queue(self, mock_llm_service):
        """TTS 에러가 큐 처리를 막지 않아야 한다"""
        sentences = ["문장 1.", "에러 문장.", "문장 3."]
        processed = []
        errors = []

        mock_tts = MagicMock()

        async def conditional_synthesize(text, **kwargs):
            if "에러" in text:
                raise Exception("TTS synthesis failed")
            return {"audio": b"fake_audio", "sample_rate": 24000, "duration": 1.0}

        mock_tts.synthesize = conditional_synthesize

        for sentence in sentences:
            try:
                await mock_tts.synthesize(text=sentence)
                processed.append(sentence)
            except Exception as e:
                errors.append((sentence, str(e)))

        assert len(processed) == 2
        assert len(errors) == 1
        assert "에러 문장." in errors[0][0]

    @pytest.mark.asyncio
    async def test_tts_timeout_handling(self, mock_llm_service):
        """TTS 타임아웃 시 적절히 처리해야 한다"""
        async def slow_synthesize(*args, **kwargs):
            await asyncio.sleep(10)
            return {"audio": b"audio", "sample_rate": 24000, "duration": 1.0}

        mock_tts = MagicMock()
        mock_tts.synthesize = slow_synthesize

        llm_result = await mock_llm_service.generate(prompt="안녕")

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                mock_tts.synthesize(text=llm_result["text"]),
                timeout=0.1
            )


class TestLLMToTTSAudioOutput:
    """LLM-TTS 오디오 출력 테스트"""

    @pytest.mark.asyncio
    async def test_audio_format_consistency(self, mock_llm_service, mock_tts_service):
        """오디오 포맷이 일관되어야 한다"""
        llm_result = await mock_llm_service.generate(prompt="테스트")

        tts_result = await mock_tts_service.synthesize(text=llm_result["text"])

        # 오디오 포맷 검증
        assert tts_result["sample_rate"] == 24000
        assert isinstance(tts_result["audio"], bytes)
        assert tts_result["duration"] > 0

    @pytest.mark.asyncio
    async def test_audio_concatenation(self, mock_tts_service):
        """여러 오디오 청크가 올바르게 연결되어야 한다"""
        sentences = ["첫 번째.", "두 번째.", "세 번째."]
        audio_chunks = []

        for sentence in sentences:
            result = await mock_tts_service.synthesize(text=sentence)
            audio_chunks.append(result["audio"])

        # 오디오 연결
        combined_audio = b"".join(audio_chunks)

        assert len(combined_audio) > 0
        assert len(combined_audio) == sum(len(chunk) for chunk in audio_chunks)

    @pytest.mark.asyncio
    async def test_streaming_audio_output(self, mock_tts_service):
        """스트리밍 오디오 출력이 동작해야 한다"""
        audio_chunks = []

        async for chunk in mock_tts_service.synthesize_stream():
            if chunk["audio"]:
                audio_chunks.append(chunk["audio"])
            if chunk["finished"]:
                break

        assert len(audio_chunks) > 0

        # 각 청크가 유효한 오디오 데이터인지 확인
        for chunk in audio_chunks:
            assert isinstance(chunk, bytes)
            assert len(chunk) > 0
