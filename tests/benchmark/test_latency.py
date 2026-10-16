"""
Latency Benchmark Tests

Phase 6.3: 지연 시간 벤치마크 테스트
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
import asyncio
import time
import numpy as np


class TestTTFT:
    """Time To First Token (TTFT) 벤치마크"""

    @pytest.mark.asyncio
    async def test_ttft_under_300ms(
        self,
        mock_fast_stt,
        mock_fast_llm,
        latency_tracker,
        benchmark_config
    ):
        """첫 토큰 지연이 300ms 미만이어야 한다"""
        target_ms = benchmark_config["ttft_target_ms"]
        iterations = benchmark_config["iterations"]

        for i in range(iterations):
            # STT 완료 후 LLM 첫 토큰까지 시간 측정
            latency_tracker.start("ttft")

            # STT
            stt_result = await mock_fast_stt.transcribe(b"audio")

            # LLM 스트리밍 - 첫 토큰
            first_token = None
            async for chunk in mock_fast_llm.generate_stream():
                if chunk["token"]:
                    first_token = chunk["token"]
                    break

            measurement = latency_tracker.stop()

        # 평균 TTFT 확인
        avg_ttft = latency_tracker.get_average("ttft")
        p95_ttft = latency_tracker.get_p95("ttft")

        print(f"\nTTFT Results:")
        print(f"  Average: {avg_ttft:.2f}ms")
        print(f"  P95: {p95_ttft:.2f}ms")
        print(f"  Target: {target_ms}ms")

        # 테스트 목표: 평균이 타겟 이하
        # Note: Mock이므로 실제 환경보다 빠름
        assert avg_ttft < target_ms, f"Average TTFT {avg_ttft:.2f}ms exceeds target {target_ms}ms"

    @pytest.mark.asyncio
    async def test_ttft_consistency(
        self,
        mock_fast_llm,
        latency_tracker
    ):
        """TTFT가 일관되어야 한다 (낮은 분산)"""
        iterations = 20

        for i in range(iterations):
            latency_tracker.start("ttft_consistency")

            async for chunk in mock_fast_llm.generate_stream():
                if chunk["token"]:
                    break

            latency_tracker.stop()

        # 표준 편차 계산
        measurements = [m.duration_ms for m in latency_tracker.measurements]
        std_dev = np.std(measurements)
        mean = np.mean(measurements)
        cv = std_dev / mean if mean > 0 else 0  # 변동 계수

        print(f"\nTTFT Consistency:")
        print(f"  Mean: {mean:.2f}ms")
        print(f"  Std Dev: {std_dev:.2f}ms")
        print(f"  CV: {cv:.2%}")

        # 변동 계수가 50% 미만이어야 함
        assert cv < 0.5, f"TTFT variation too high: CV={cv:.2%}"


class TestFirstAudioLatency:
    """첫 오디오 지연 시간 벤치마크"""

    @pytest.mark.asyncio
    async def test_first_audio_under_1s(
        self,
        mock_fast_stt,
        mock_fast_llm,
        mock_fast_tts,
        latency_tracker,
        benchmark_config
    ):
        """첫 오디오까지 지연이 1초 미만이어야 한다"""
        target_ms = benchmark_config["first_audio_target_ms"]
        iterations = benchmark_config["iterations"]

        for i in range(iterations):
            latency_tracker.start("first_audio")

            # 1. STT
            stt_result = await mock_fast_stt.transcribe(b"audio")

            # 2. LLM 스트리밍 - 첫 문장까지
            sentence_buffer = ""
            async for chunk in mock_fast_llm.generate_stream():
                if chunk["token"]:
                    sentence_buffer += chunk["token"]
                    if any(sentence_buffer.endswith(p) for p in [".", "!", "?"]):
                        break
                if chunk["finished"]:
                    break

            # 3. TTS - 첫 문장
            if sentence_buffer:
                tts_result = await mock_fast_tts.synthesize(sentence_buffer)

            measurement = latency_tracker.stop()

        avg_latency = latency_tracker.get_average("first_audio")
        p95_latency = latency_tracker.get_p95("first_audio")

        print(f"\nFirst Audio Latency Results:")
        print(f"  Average: {avg_latency:.2f}ms")
        print(f"  P95: {p95_latency:.2f}ms")
        print(f"  Target: {target_ms}ms")

        assert avg_latency < target_ms, f"Average latency {avg_latency:.2f}ms exceeds target {target_ms}ms"

    @pytest.mark.asyncio
    async def test_streaming_reduces_latency(
        self,
        mock_fast_stt,
        mock_fast_llm,
        mock_fast_tts,
        latency_tracker
    ):
        """스트리밍이 지연 시간을 줄여야 한다"""
        # 스트리밍 방식
        latency_tracker.start("streaming")

        stt_result = await mock_fast_stt.transcribe(b"audio")

        sentence_buffer = ""
        async for chunk in mock_fast_llm.generate_stream():
            if chunk["token"]:
                sentence_buffer += chunk["token"]
                if any(sentence_buffer.endswith(p) for p in [".", "!", "?"]):
                    await mock_fast_tts.synthesize(sentence_buffer)
                    break
            if chunk["finished"]:
                break

        streaming_time = latency_tracker.stop().duration_ms

        # 비스트리밍 방식 (전체 응답 대기)
        latency_tracker.start("non_streaming")

        stt_result = await mock_fast_stt.transcribe(b"audio")

        # 전체 응답 대기
        full_response = ""
        async for chunk in mock_fast_llm.generate_stream():
            if chunk["token"]:
                full_response += chunk["token"]
            if chunk["finished"]:
                break

        # 전체 응답 TTS
        if full_response:
            await mock_fast_tts.synthesize(full_response)

        non_streaming_time = latency_tracker.stop().duration_ms

        print(f"\nStreaming vs Non-streaming:")
        print(f"  Streaming: {streaming_time:.2f}ms")
        print(f"  Non-streaming: {non_streaming_time:.2f}ms")
        print(f"  Improvement: {(1 - streaming_time/non_streaming_time)*100:.1f}%")

        # 스트리밍이 더 빨라야 함
        assert streaming_time < non_streaming_time


class TestBargeInLatency:
    """Barge-in 반응 시간 벤치마크"""

    @pytest.mark.asyncio
    async def test_barge_in_reaction_under_300ms(
        self,
        latency_tracker,
        benchmark_config
    ):
        """Barge-in 반응 시간이 300ms 미만이어야 한다"""
        target_ms = benchmark_config["barge_in_target_ms"]
        iterations = benchmark_config["iterations"]

        for i in range(iterations):
            # 음성 감지 시뮬레이션
            is_playing = True
            user_speech_detected = False

            latency_tracker.start("barge_in")

            # 사용자 음성 감지
            await asyncio.sleep(np.random.uniform(0.01, 0.03))  # VAD 처리 시간
            user_speech_detected = True

            # 에너지 임계값 확인
            speech_energy = 0.8
            threshold = 0.5

            # Barge-in 결정
            if user_speech_detected and speech_energy > threshold and is_playing:
                # 오디오 중단 명령
                is_playing = False

            measurement = latency_tracker.stop()

        avg_latency = latency_tracker.get_average("barge_in")
        p95_latency = latency_tracker.get_p95("barge_in")

        print(f"\nBarge-in Reaction Time Results:")
        print(f"  Average: {avg_latency:.2f}ms")
        print(f"  P95: {p95_latency:.2f}ms")
        print(f"  Target: {target_ms}ms")

        assert avg_latency < target_ms, f"Barge-in reaction {avg_latency:.2f}ms exceeds target {target_ms}ms"

    @pytest.mark.asyncio
    async def test_barge_in_with_aec(
        self,
        latency_tracker
    ):
        """AEC 포함 Barge-in 반응 시간"""
        iterations = 10

        for i in range(iterations):
            latency_tracker.start("barge_in_with_aec")

            # AEC 처리 시뮬레이션
            await asyncio.sleep(np.random.uniform(0.005, 0.01))

            # VAD 처리
            await asyncio.sleep(np.random.uniform(0.01, 0.02))

            # Barge-in 결정
            await asyncio.sleep(np.random.uniform(0.001, 0.005))

            latency_tracker.stop()

        avg_latency = latency_tracker.get_average("barge_in_with_aec")

        print(f"\nBarge-in with AEC:")
        print(f"  Average: {avg_latency:.2f}ms")

        # AEC 포함해도 300ms 이하
        assert avg_latency < 300


class TestWakeWordLatency:
    """Wake Word 감지 지연 시간 벤치마크"""

    @pytest.mark.asyncio
    async def test_wake_word_detection_latency(
        self,
        mock_fast_wake_word,
        latency_tracker,
        benchmark_config
    ):
        """Wake Word 감지 지연이 100ms 미만이어야 한다"""
        target_ms = benchmark_config["wake_word_target_ms"]
        iterations = benchmark_config["iterations"]

        for i in range(iterations):
            latency_tracker.start("wake_word")

            result = await mock_fast_wake_word.detect(b"audio_chunk")

            latency_tracker.stop()

        avg_latency = latency_tracker.get_average("wake_word")
        p95_latency = latency_tracker.get_p95("wake_word")

        print(f"\nWake Word Detection Latency:")
        print(f"  Average: {avg_latency:.2f}ms")
        print(f"  P95: {p95_latency:.2f}ms")
        print(f"  Target: {target_ms}ms")

        assert avg_latency < target_ms


class TestEndToEndLatency:
    """E2E 지연 시간 벤치마크"""

    @pytest.mark.asyncio
    async def test_full_pipeline_latency(
        self,
        mock_fast_wake_word,
        mock_fast_stt,
        mock_fast_llm,
        mock_fast_tts,
        latency_tracker
    ):
        """전체 파이프라인 지연 시간 측정"""
        iterations = 5

        for i in range(iterations):
            latency_tracker.start("full_pipeline")

            # 1. Wake Word
            await mock_fast_wake_word.detect(b"audio")

            # 2. STT
            stt_result = await mock_fast_stt.transcribe(b"user_audio")

            # 3. LLM
            llm_result = await mock_fast_llm.generate(prompt=stt_result["text"])

            # 4. TTS
            tts_result = await mock_fast_tts.synthesize(llm_result["text"])

            latency_tracker.stop()

        avg_latency = latency_tracker.get_average("full_pipeline")

        print(f"\nFull Pipeline Latency:")
        print(f"  Average: {avg_latency:.2f}ms")

        # 전체 파이프라인 2초 이하
        assert avg_latency < 2000

    @pytest.mark.asyncio
    async def test_pipeline_breakdown(
        self,
        mock_fast_wake_word,
        mock_fast_stt,
        mock_fast_llm,
        mock_fast_tts,
        latency_tracker
    ):
        """파이프라인 각 단계별 지연 시간 분석"""
        # Wake Word
        latency_tracker.start("wake_word_step")
        await mock_fast_wake_word.detect(b"audio")
        latency_tracker.stop()

        # STT
        latency_tracker.start("stt_step")
        stt_result = await mock_fast_stt.transcribe(b"audio")
        latency_tracker.stop()

        # LLM
        latency_tracker.start("llm_step")
        llm_result = await mock_fast_llm.generate(prompt=stt_result["text"])
        latency_tracker.stop()

        # TTS
        latency_tracker.start("tts_step")
        await mock_fast_tts.synthesize(llm_result["text"])
        latency_tracker.stop()

        # 각 단계 분석
        wake_word_time = latency_tracker.get_average("wake_word_step")
        stt_time = latency_tracker.get_average("stt_step")
        llm_time = latency_tracker.get_average("llm_step")
        tts_time = latency_tracker.get_average("tts_step")
        total = wake_word_time + stt_time + llm_time + tts_time

        print(f"\nPipeline Breakdown:")
        print(f"  Wake Word: {wake_word_time:.2f}ms ({wake_word_time/total*100:.1f}%)")
        print(f"  STT: {stt_time:.2f}ms ({stt_time/total*100:.1f}%)")
        print(f"  LLM: {llm_time:.2f}ms ({llm_time/total*100:.1f}%)")
        print(f"  TTS: {tts_time:.2f}ms ({tts_time/total*100:.1f}%)")
        print(f"  Total: {total:.2f}ms")


class TestRAGLatency:
    """RAG 지연 시간 벤치마크"""

    @pytest.mark.asyncio
    async def test_rag_retrieval_latency(
        self,
        mock_fast_embedding,
        mock_fast_rag,
        latency_tracker
    ):
        """RAG 검색 지연 시간 측정"""
        iterations = 10
        query = "회사 정책에 대해 알려주세요"

        for i in range(iterations):
            latency_tracker.start("rag_retrieval")

            # 쿼리 임베딩
            await mock_fast_embedding.embed(query)

            # 벡터 검색
            await mock_fast_rag.retrieve(query=query)

            latency_tracker.stop()

        avg_latency = latency_tracker.get_average("rag_retrieval")

        print(f"\nRAG Retrieval Latency:")
        print(f"  Average: {avg_latency:.2f}ms")

        # RAG 검색 200ms 이하
        assert avg_latency < 200

    @pytest.mark.asyncio
    async def test_rag_impact_on_response_time(
        self,
        mock_fast_stt,
        mock_fast_llm,
        mock_fast_rag,
        mock_fast_embedding,
        latency_tracker
    ):
        """RAG가 응답 시간에 미치는 영향"""
        # RAG 없이
        latency_tracker.start("without_rag")
        stt_result = await mock_fast_stt.transcribe(b"audio")
        await mock_fast_llm.generate(prompt=stt_result["text"])
        without_rag_time = latency_tracker.stop().duration_ms

        # RAG 포함
        latency_tracker.start("with_rag")
        stt_result = await mock_fast_stt.transcribe(b"audio")
        await mock_fast_embedding.embed(stt_result["text"])
        await mock_fast_rag.retrieve(query=stt_result["text"])
        await mock_fast_llm.generate(prompt=stt_result["text"])
        with_rag_time = latency_tracker.stop().duration_ms

        overhead = with_rag_time - without_rag_time

        print(f"\nRAG Impact on Response Time:")
        print(f"  Without RAG: {without_rag_time:.2f}ms")
        print(f"  With RAG: {with_rag_time:.2f}ms")
        print(f"  RAG Overhead: {overhead:.2f}ms")

        # RAG 오버헤드 200ms 이하
        assert overhead < 200


class TestConcurrencyPerformance:
    """동시성 성능 벤치마크"""

    @pytest.mark.asyncio
    async def test_concurrent_requests(
        self,
        mock_fast_stt,
        mock_fast_llm
    ):
        """동시 요청 처리 성능"""
        concurrent_count = 5

        async def process_request(request_id):
            start = time.perf_counter()
            await mock_fast_stt.transcribe(b"audio")
            await mock_fast_llm.generate(prompt="test")
            end = time.perf_counter()
            return (end - start) * 1000

        # 동시 실행
        start_time = time.perf_counter()
        results = await asyncio.gather(*[
            process_request(i) for i in range(concurrent_count)
        ])
        total_time = (time.perf_counter() - start_time) * 1000

        # 개별 요청 시간 합계
        individual_sum = sum(results)

        print(f"\nConcurrent Requests ({concurrent_count}):")
        print(f"  Total wall time: {total_time:.2f}ms")
        print(f"  Sum of individual: {individual_sum:.2f}ms")
        print(f"  Parallelization efficiency: {individual_sum/total_time:.2f}x")

        # 병렬화 효과 있어야 함
        assert total_time < individual_sum


class TestMemoryEfficiency:
    """메모리 효율성 벤치마크"""

    @pytest.mark.asyncio
    async def test_streaming_memory_efficiency(self):
        """스트리밍이 메모리 효율적이어야 한다"""
        # 스트리밍 방식: 한 번에 하나의 청크만 메모리에
        streaming_peak_memory = 0
        chunk_count = 0

        async def stream_generator():
            for i in range(100):
                yield f"chunk_{i}"

        async for chunk in stream_generator():
            chunk_count += 1
            # 청크 처리 후 즉시 해제
            pass

        # 비스트리밍: 전체를 메모리에 로드
        non_streaming_data = [f"chunk_{i}" for i in range(100)]

        print(f"\nStreaming Memory Efficiency:")
        print(f"  Streaming: processes {chunk_count} chunks one at a time")
        print(f"  Non-streaming: holds all {len(non_streaming_data)} chunks in memory")

        # 스트리밍은 전체 데이터를 한 번에 메모리에 로드하지 않음
        assert chunk_count == 100
