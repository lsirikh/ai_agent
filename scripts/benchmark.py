#!/usr/bin/env python3
"""
EdgeVoice Performance Benchmark Script

Phase 6.3: 성능 벤치마크 실행 스크립트
실제 서비스에 대한 성능 측정을 수행합니다.
"""
import asyncio
import time
import argparse
import json
import statistics
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import httpx
    import numpy as np
except ImportError:
    print("Required packages not installed. Run: pip install httpx numpy")
    sys.exit(1)


@dataclass
class BenchmarkResult:
    """벤치마크 결과"""
    name: str
    iterations: int
    mean_ms: float
    median_ms: float
    std_ms: float
    min_ms: float
    max_ms: float
    p95_ms: float
    p99_ms: float
    success_rate: float
    errors: List[str]


@dataclass
class BenchmarkReport:
    """벤치마크 리포트"""
    timestamp: str
    configuration: Dict[str, Any]
    results: List[BenchmarkResult]
    summary: Dict[str, Any]


class PerformanceBenchmark:
    """성능 벤치마크 실행기"""

    def __init__(
        self,
        backend_url: str = "http://localhost:11000",
        stt_url: str = "http://localhost:11001",
        tts_url: str = "http://localhost:11002",
        llm_url: str = "http://localhost:11003",
        embedding_url: str = "http://localhost:11004",
        iterations: int = 10,
        warmup: int = 2
    ):
        self.backend_url = backend_url
        self.stt_url = stt_url
        self.tts_url = tts_url
        self.llm_url = llm_url
        self.embedding_url = embedding_url
        self.iterations = iterations
        self.warmup = warmup
        self.results: List[BenchmarkResult] = []

    def _calculate_stats(
        self,
        name: str,
        latencies: List[float],
        errors: List[str]
    ) -> BenchmarkResult:
        """통계 계산"""
        if not latencies:
            return BenchmarkResult(
                name=name,
                iterations=0,
                mean_ms=0,
                median_ms=0,
                std_ms=0,
                min_ms=0,
                max_ms=0,
                p95_ms=0,
                p99_ms=0,
                success_rate=0,
                errors=errors
            )

        latencies_sorted = sorted(latencies)
        total_attempts = len(latencies) + len(errors)

        return BenchmarkResult(
            name=name,
            iterations=len(latencies),
            mean_ms=statistics.mean(latencies),
            median_ms=statistics.median(latencies),
            std_ms=statistics.stdev(latencies) if len(latencies) > 1 else 0,
            min_ms=min(latencies),
            max_ms=max(latencies),
            p95_ms=latencies_sorted[int(len(latencies) * 0.95)] if latencies else 0,
            p99_ms=latencies_sorted[int(len(latencies) * 0.99)] if latencies else 0,
            success_rate=len(latencies) / total_attempts * 100 if total_attempts > 0 else 0,
            errors=errors
        )

    async def _measure_latency(
        self,
        name: str,
        func,
        iterations: int
    ) -> BenchmarkResult:
        """지연 시간 측정"""
        latencies = []
        errors = []

        # Warmup
        print(f"  Warming up {name}...")
        for _ in range(self.warmup):
            try:
                await func()
            except Exception:
                pass

        # Actual measurements
        print(f"  Running {iterations} iterations...")
        for i in range(iterations):
            try:
                start = time.perf_counter()
                await func()
                end = time.perf_counter()
                latencies.append((end - start) * 1000)
                print(f"    Iteration {i+1}/{iterations}: {latencies[-1]:.2f}ms")
            except Exception as e:
                errors.append(str(e))
                print(f"    Iteration {i+1}/{iterations}: ERROR - {e}")

        return self._calculate_stats(name, latencies, errors)

    async def benchmark_stt(self) -> BenchmarkResult:
        """STT 서비스 벤치마크"""
        print("\n📊 Benchmarking STT Service...")

        # 테스트용 오디오 데이터 (1초, 16kHz, 16-bit)
        sample_rate = 16000
        duration = 1.0
        samples = int(sample_rate * duration)
        audio_data = np.random.randint(-32768, 32767, size=samples, dtype=np.int16).tobytes()

        async def stt_request():
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.stt_url}/transcribe",
                    files={"audio": ("audio.wav", audio_data, "audio/wav")}
                )
                response.raise_for_status()
                return response.json()

        return await self._measure_latency("STT", stt_request, self.iterations)

    async def benchmark_llm(self) -> BenchmarkResult:
        """LLM 서비스 벤치마크"""
        print("\n📊 Benchmarking LLM Service...")

        async def llm_request():
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.llm_url}/generate",
                    json={
                        "prompt": "안녕하세요, 오늘 날씨가 어때요?",
                        "max_tokens": 100
                    }
                )
                response.raise_for_status()
                return response.json()

        return await self._measure_latency("LLM", llm_request, self.iterations)

    async def benchmark_llm_streaming(self) -> BenchmarkResult:
        """LLM 스트리밍 TTFT 벤치마크"""
        print("\n📊 Benchmarking LLM Streaming (TTFT)...")

        latencies = []
        errors = []

        # Warmup
        print("  Warming up...")
        for _ in range(self.warmup):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    async with client.stream(
                        "POST",
                        f"{self.llm_url}/generate/stream",
                        json={"prompt": "Hello", "max_tokens": 10}
                    ) as response:
                        async for _ in response.aiter_lines():
                            break
            except Exception:
                pass

        # Actual measurements
        print(f"  Running {self.iterations} iterations...")
        for i in range(self.iterations):
            try:
                start = time.perf_counter()
                async with httpx.AsyncClient(timeout=60.0) as client:
                    async with client.stream(
                        "POST",
                        f"{self.llm_url}/generate/stream",
                        json={"prompt": "안녕하세요", "max_tokens": 50}
                    ) as response:
                        async for _ in response.aiter_lines():
                            end = time.perf_counter()
                            latencies.append((end - start) * 1000)
                            print(f"    Iteration {i+1}/{self.iterations}: {latencies[-1]:.2f}ms")
                            break
            except Exception as e:
                errors.append(str(e))
                print(f"    Iteration {i+1}/{self.iterations}: ERROR - {e}")

        return self._calculate_stats("LLM_TTFT", latencies, errors)

    async def benchmark_tts(self) -> BenchmarkResult:
        """TTS 서비스 벤치마크"""
        print("\n📊 Benchmarking TTS Service...")

        async def tts_request():
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.tts_url}/synthesize",
                    json={"text": "안녕하세요, 무엇을 도와드릴까요?"}
                )
                response.raise_for_status()
                return response.content

        return await self._measure_latency("TTS", tts_request, self.iterations)

    async def benchmark_embedding(self) -> BenchmarkResult:
        """Embedding 서비스 벤치마크"""
        print("\n📊 Benchmarking Embedding Service...")

        async def embedding_request():
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.embedding_url}/embed",
                    json={"text": "오늘 날씨가 어떻습니까?"}
                )
                response.raise_for_status()
                return response.json()

        return await self._measure_latency("Embedding", embedding_request, self.iterations)

    async def benchmark_full_pipeline(self) -> BenchmarkResult:
        """전체 파이프라인 벤치마크 (STT → LLM → TTS)"""
        print("\n📊 Benchmarking Full Pipeline (STT → LLM → TTS)...")

        sample_rate = 16000
        audio_data = np.random.randint(-32768, 32767, size=sample_rate, dtype=np.int16).tobytes()

        async def pipeline_request():
            async with httpx.AsyncClient(timeout=120.0) as client:
                # STT
                stt_response = await client.post(
                    f"{self.stt_url}/transcribe",
                    files={"audio": ("audio.wav", audio_data, "audio/wav")}
                )
                stt_response.raise_for_status()
                text = stt_response.json().get("text", "안녕하세요")

                # LLM
                llm_response = await client.post(
                    f"{self.llm_url}/generate",
                    json={"prompt": text, "max_tokens": 100}
                )
                llm_response.raise_for_status()
                response_text = llm_response.json().get("text", "")

                # TTS
                tts_response = await client.post(
                    f"{self.tts_url}/synthesize",
                    json={"text": response_text}
                )
                tts_response.raise_for_status()
                return tts_response.content

        return await self._measure_latency("Full_Pipeline", pipeline_request, self.iterations)

    async def benchmark_backend_health(self) -> BenchmarkResult:
        """백엔드 헬스체크 벤치마크"""
        print("\n📊 Benchmarking Backend Health Check...")

        async def health_request():
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.backend_url}/api/status")
                response.raise_for_status()
                return response.json()

        return await self._measure_latency("Backend_Health", health_request, self.iterations)

    async def run_all(self, services: Optional[List[str]] = None) -> BenchmarkReport:
        """모든 벤치마크 실행"""
        print("=" * 60)
        print("EdgeVoice Performance Benchmark")
        print("=" * 60)
        print(f"Iterations: {self.iterations}")
        print(f"Warmup: {self.warmup}")
        print(f"Backend URL: {self.backend_url}")

        available_benchmarks = {
            "backend": self.benchmark_backend_health,
            "stt": self.benchmark_stt,
            "llm": self.benchmark_llm,
            "llm_streaming": self.benchmark_llm_streaming,
            "tts": self.benchmark_tts,
            "embedding": self.benchmark_embedding,
            "pipeline": self.benchmark_full_pipeline
        }

        if services is None:
            services = list(available_benchmarks.keys())

        results = []
        for service in services:
            if service in available_benchmarks:
                try:
                    result = await available_benchmarks[service]()
                    results.append(result)
                except Exception as e:
                    print(f"\n❌ Failed to benchmark {service}: {e}")
                    results.append(BenchmarkResult(
                        name=service,
                        iterations=0,
                        mean_ms=0,
                        median_ms=0,
                        std_ms=0,
                        min_ms=0,
                        max_ms=0,
                        p95_ms=0,
                        p99_ms=0,
                        success_rate=0,
                        errors=[str(e)]
                    ))

        # Summary
        summary = self._generate_summary(results)

        report = BenchmarkReport(
            timestamp=datetime.now().isoformat(),
            configuration={
                "iterations": self.iterations,
                "warmup": self.warmup,
                "backend_url": self.backend_url,
                "stt_url": self.stt_url,
                "tts_url": self.tts_url,
                "llm_url": self.llm_url,
                "embedding_url": self.embedding_url
            },
            results=results,
            summary=summary
        )

        return report

    def _generate_summary(self, results: List[BenchmarkResult]) -> Dict[str, Any]:
        """요약 생성"""
        # PRD 기준
        targets = {
            "LLM_TTFT": 300,  # 첫 토큰 지연 < 300ms
            "Full_Pipeline": 1000,  # 첫 음성 < 1초
            "STT": 500,
            "TTS": 500,
            "Embedding": 100
        }

        passed = 0
        failed = 0
        warnings = []

        for result in results:
            if result.name in targets:
                target = targets[result.name]
                if result.p95_ms > 0 and result.p95_ms <= target:
                    passed += 1
                elif result.p95_ms > target:
                    failed += 1
                    warnings.append(
                        f"{result.name}: P95 {result.p95_ms:.2f}ms exceeds target {target}ms"
                    )

        return {
            "total_benchmarks": len(results),
            "passed": passed,
            "failed": failed,
            "warnings": warnings
        }

    def print_report(self, report: BenchmarkReport):
        """리포트 출력"""
        print("\n" + "=" * 60)
        print("BENCHMARK RESULTS")
        print("=" * 60)

        for result in report.results:
            print(f"\n📈 {result.name}")
            print(f"   Iterations: {result.iterations}")
            print(f"   Success Rate: {result.success_rate:.1f}%")
            if result.mean_ms > 0:
                print(f"   Mean: {result.mean_ms:.2f}ms")
                print(f"   Median: {result.median_ms:.2f}ms")
                print(f"   Std: {result.std_ms:.2f}ms")
                print(f"   Min: {result.min_ms:.2f}ms")
                print(f"   Max: {result.max_ms:.2f}ms")
                print(f"   P95: {result.p95_ms:.2f}ms")
                print(f"   P99: {result.p99_ms:.2f}ms")
            if result.errors:
                print(f"   Errors: {len(result.errors)}")

        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        summary = report.summary
        print(f"Total Benchmarks: {summary['total_benchmarks']}")
        print(f"Passed: {summary['passed']}")
        print(f"Failed: {summary['failed']}")

        if summary['warnings']:
            print("\n⚠️  Warnings:")
            for warning in summary['warnings']:
                print(f"   - {warning}")

        # PRD 기준 체크
        print("\n📋 PRD Requirements Check:")
        for result in report.results:
            if result.name == "LLM_TTFT":
                status = "✅" if result.p95_ms <= 300 else "❌"
                print(f"   {status} TTFT < 300ms: {result.p95_ms:.2f}ms")
            elif result.name == "Full_Pipeline":
                status = "✅" if result.p95_ms <= 1000 else "❌"
                print(f"   {status} First Audio < 1s: {result.p95_ms:.2f}ms")


def main():
    parser = argparse.ArgumentParser(description="EdgeVoice Performance Benchmark")
    parser.add_argument(
        "--backend-url",
        default="http://localhost:11000",
        help="Backend API URL"
    )
    parser.add_argument(
        "--stt-url",
        default="http://localhost:11001",
        help="STT Service URL"
    )
    parser.add_argument(
        "--tts-url",
        default="http://localhost:11002",
        help="TTS Service URL"
    )
    parser.add_argument(
        "--llm-url",
        default="http://localhost:11003",
        help="LLM Service URL"
    )
    parser.add_argument(
        "--embedding-url",
        default="http://localhost:11004",
        help="Embedding Service URL"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=10,
        help="Number of iterations per benchmark"
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=2,
        help="Number of warmup iterations"
    )
    parser.add_argument(
        "--services",
        nargs="+",
        choices=["backend", "stt", "llm", "llm_streaming", "tts", "embedding", "pipeline"],
        help="Services to benchmark (default: all)"
    )
    parser.add_argument(
        "--output",
        help="Output file for JSON report"
    )

    args = parser.parse_args()

    benchmark = PerformanceBenchmark(
        backend_url=args.backend_url,
        stt_url=args.stt_url,
        tts_url=args.tts_url,
        llm_url=args.llm_url,
        embedding_url=args.embedding_url,
        iterations=args.iterations,
        warmup=args.warmup
    )

    report = asyncio.run(benchmark.run_all(args.services))
    benchmark.print_report(report)

    if args.output:
        # Convert to JSON-serializable format
        report_dict = {
            "timestamp": report.timestamp,
            "configuration": report.configuration,
            "results": [asdict(r) for r in report.results],
            "summary": report.summary
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, indent=2, ensure_ascii=False)
        print(f"\n📄 Report saved to: {args.output}")


if __name__ == "__main__":
    main()
