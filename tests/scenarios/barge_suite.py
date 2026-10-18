"""
끼어들기(barge-in) 시험 수백 개 (사용자 요청 2026-10-18: '발지인 해도 하나도 안 먹혀 —
수백 가지 정도를 네 스스로 해 봐').

    python tests/scenarios/barge_suite.py            # A·B·C 전부
    python tests/scenarios/barge_suite.py --parts A  # 일부만

A. 말소리 끼어들기(호출어 없이): 게이트웨이의 끼어들기 코드(PlaybackTracker ·
   EchoDelay · SpeechBargeIn)를 그대로 불러, 실제 답 음성의 에코(크기·시차)와
   한국어 목소리를 섞는다.
B. '헤이 자비스' 끼어들기: 에코를 섞은 호출어를 돌고 있는 웨이크워드 서비스에 넣는다
   (답하는 중 상태로 두고 — 기준을 낮추는 모드).
C. 전체 파이프라인(게이트웨이·웨이크워드·오케스트레이터·LLM·TTS): 말소리·호출어
   끼어들기와
   [중단] 버튼.

판정: 에코가 목소리보다 작으면(에코 0.3배 이하) 끊겨야 하고, 에코만 있으면 절대
끊기면 안
된다. 에코가 목소리만큼 크면(0.5배 이상) 소리 크기로는 가를 수 없어 '한계' 로 따로 센다.
만드는 파일은 Downloads/Tests/scenarios 아래뿐이다.
"""

import argparse
import asyncio
import json
import subprocess
import sys
import time
import wave
from itertools import product
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "services" / "audio_gateway"))

import run  # noqa: E402

AUDIO = run.AUDIO
OUT = run.OUT / "barge.json"
REDIS = run.REDIS
WAKE_CHANNEL = "edgevoice:wake_word:detected"
STATE_CHANNEL = "edgevoice:orchestrator:state"
AUDIO_INPUT = "edgevoice:audio:input"

QUESTIONS = ["지금 몇 시야", "서울 날씨 어때", "파이썬이 뭐야"]
WAKES = [
    ("wake.wav", None),
    ("헤이 자비스", 0),
    ("헤이 자비스", -2),
    ("헤이, 자비스", 2),
]
LIMIT_GAIN = 0.5  # 이 이상이면 에코가 목소리만큼 크다 — 소리 크기로는 가를 수 없다


def synth(text: str, rate: int = 0) -> Path:
    """한국어 음성(Heami) WAV — 속도(rate -10~10)별로. Downloads/Tests 에 둔다."""
    path = AUDIO / f"{run._audio_name(f'{text}|{rate}')}.wav"
    if path.exists():
        return path
    quoted = text.replace("'", "''")
    script = AUDIO / "synth_rate.ps1"
    script.write_text(
        "\n".join(
            [
                "Add-Type -AssemblyName System.Speech",
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer",
                "$v = $s.GetInstalledVoices() | "
                "? { $_.VoiceInfo.Culture.Name -eq 'ko-KR' }"
                " | select -First 1",
                "$s.SelectVoice($v.VoiceInfo.Name)",
                f"$s.Rate = {rate}",
                "$f = New-Object "
                "System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, "
                "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, "
                "[System.Speech.AudioFormat.AudioChannel]::Mono)",
                f"$s.SetOutputToWaveFile('{path}', $f); $s.Speak('{quoted}')",
                "$s.SetOutputToNull()",
            ]
        ),
        encoding="utf-8-sig",
    )
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        check=True,
        capture_output=True,
    )
    return path


def read16(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16) / 32768.0


def answer16() -> np.ndarray:
    ans = np.load(AUDIO / "answer.npy")  # 실제 TTS 답(24kHz float32)
    return np.interp(np.arange(0, len(ans), 1.5), np.arange(len(ans)), ans), ans


# ── A. 말소리 끼어들기(게이트웨이 코드로) ─────────────────────
def part_a() -> list:
    from app.speech_barge_in import EchoDelay, PlaybackTracker, SpeechBargeIn

    a16, a24 = answer16()
    voices = {q: read16(synth(q)) for q in QUESTIONS}

    class Clock:
        now = 1000.0

        def __call__(self):
            return self.now

    def simulate(gain, delay, user_at, voice, warm, noise):
        clock = Clock()
        tracker = PlaybackTracker(clock=clock)
        echo_delay, barge = EchoDelay(), SpeechBargeIn()
        rng = np.random.default_rng(7)
        if warm:  # 앞 답에서 이미 에코를 익힌 상태(게이트웨이는 한 번 익히면 유지한다)
            tracker.add(a24[: 24000 * 12].astype(np.float32))
            for i in range(120):
                clock.now += 0.1
                j = i - int(round(delay * 10))
                mic = (
                    gain * a16[j * 1600 : (j + 1) * 1600] if j >= 0 else np.zeros(1600)
                )
                rms = float(np.sqrt(np.mean(mic**2)))
                far = echo_delay.far_level(tracker)
                if echo_delay.observe(rms, tracker):
                    barge.forget_echo(echo_delay.recent_ratios(tracker, barge.min_far))
                barge.feed(
                    rms, 0.95 if rms > 0.01 else 0.05, far, learn=echo_delay.known
                )
            barge.reset()
            clock.now += 2.0
        start = clock.now
        tracker.add(a24[24000 * 12 :].astype(np.float32))
        offset = 120
        for i in range(int(min(len(a16) / 1600 - offset, 300))):
            clock.now = start + (i + 1) * 0.1
            j = offset + i - int(round(delay * 10))
            mic = (
                gain * a16[j * 1600 : (j + 1) * 1600] if j >= offset else np.zeros(1600)
            )
            mic = mic + noise * rng.standard_normal(1600)
            if voice is not None and i >= user_at * 10:
                k = i - int(user_at * 10)
                part = voice[k * 1600 : (k + 1) * 1600]
                mic = mic + np.pad(part, (0, 1600 - len(part)))
            rms = float(np.sqrt(np.mean(mic**2)))
            far = echo_delay.far_level(tracker)
            if echo_delay.observe(rms, tracker):
                barge.forget_echo(echo_delay.recent_ratios(tracker, barge.min_far))
            vad = 0.95 if rms > 0.01 else 0.05  # 에코도 사람 말소리라 VAD 는 높다
            if barge.feed(rms, vad, far, learn=echo_delay.known):
                return round(clock.now - start, 1)
        return None

    out = []
    for gain, delay, warm, noise in product(
        [0.0, 0.1, 0.2, 0.3, 0.5, 0.8],
        [0.0, 0.3, 0.6, 1.0],
        [True, False],
        [0.0, 0.003],
    ):
        hit = simulate(gain, delay, None, None, warm, noise)
        out.append(
            {
                "part": "A",
                "kind": "에코만",
                "gain": gain,
                "delay": delay,
                "warm": warm,
                "noise": noise,
                "result": hit,
                "status": "pass" if hit is None else "fail",
                "note": "" if hit is None else f"에코만 있는데 {hit}초에 끊었다",
            }
        )
    for gain, delay, user_at, q, warm in product(
        [0.0, 0.1, 0.2, 0.3, 0.5, 0.8],
        [0.0, 0.3, 0.6],
        [2.0, 6.0],
        QUESTIONS,
        [True, False],
    ):
        hit = simulate(gain, delay, user_at, voices[q], warm, 0.0)
        late = None if hit is None else round(hit - user_at, 1)
        ok = late is not None and 0 <= late <= 1.0
        status = "pass" if ok else ("limit" if gain >= LIMIT_GAIN else "fail")
        out.append(
            {
                "part": "A",
                "kind": "말소리",
                "gain": gain,
                "delay": delay,
                "warm": warm,
                "user_at": user_at,
                "question": q,
                "result": late,
                "status": status,
                "note": ""
                if ok
                else ("끊지 못했다" if late is None else f"{late}초 걸렸다"),
            }
        )
    return out


# ── B. '헤이 자비스' 끼어들기(돌고 있는 웨이크워드 서비스) ─────
async def part_b() -> list:
    a16, _ = answer16()
    wakes = []
    for name, rate in WAKES:
        path = AUDIO / name if rate is None else synth(name, rate)
        wakes.append(
            (f"{name}{'' if rate is None else f'(속도 {rate})'}", read16(path))
        )
    r = run.redis_client()
    ps = r.pubsub()
    await ps.subscribe(WAKE_CHANNEL)
    out = []

    async def state(name):
        await r.publish(
            STATE_CHANNEL, json.dumps({"type": "state_change", "new_state": name})
        )

    async def drain_events():
        hits = 0
        while True:
            m = await ps.get_message(ignore_subscribe_messages=True, timeout=0.05)
            if not m:
                return hits
            hits += 1

    try:
        for (label, wake), gain, delay, at in product(
            wakes, [0.0, 0.1, 0.2, 0.3, 0.5, 0.8], [0.0, 0.6], [3.0]
        ):
            await drain_events()
            await state("SPEAKING")  # 답하는 중 — 호출어 기준을 낮추는 모드
            await asyncio.sleep(0.3)
            seconds = at + len(wake) / 16000 + 2.0
            start = 2400 * 0  # 답 앞부분부터
            echo = gain * a16[start : start + int(16000 * seconds)]
            shift = int(16000 * delay)
            mic = np.concatenate([np.zeros(shift), echo])[: int(16000 * seconds)]
            w0 = int(16000 * at)
            mic[w0 : w0 + len(wake)] += wake
            began = time.perf_counter()
            hit_at = None
            for n, i in enumerate(range(0, len(mic), 1600)):
                await r.publish(
                    AUDIO_INPUT,
                    np.clip(mic[i : i + 1600], -1, 1).astype(np.float32).tobytes(),
                )
                m = await ps.get_message(ignore_subscribe_messages=True, timeout=0)
                if m and hit_at is None:
                    hit_at = round(time.perf_counter() - began - at, 1)
                pause = began + (n + 1) * 0.1 - time.perf_counter()
                if pause > 0:
                    await asyncio.sleep(pause)
            for _ in range(30):  # STT 확인 경로는 조금 늦게 온다
                m = await ps.get_message(ignore_subscribe_messages=True, timeout=0.1)
                if m and hit_at is None:
                    hit_at = round(time.perf_counter() - began - at, 1)
            await state("READY")
            ok = hit_at is not None
            status = "pass" if ok else ("limit" if gain >= LIMIT_GAIN else "fail")
            out.append(
                {
                    "part": "B",
                    "kind": "호출어",
                    "wake": label,
                    "gain": gain,
                    "delay": delay,
                    "result": hit_at,
                    "status": status,
                    "note": "" if ok else "호출어를 듣지 못했다",
                }
            )
            print("B", label, gain, delay, hit_at, flush=True)
            await asyncio.sleep(9.5)  # 감지로 시작된 듣기가 끝나기를 기다린다
    finally:
        await state("READY")
        await r.aclose()
    return out


# ── C. 전체 파이프라인 ────────────────────────────────────────
async def part_c() -> list:
    import httpx

    out = []
    wake = Path(run.AUDIO / "wake.wav")
    run.synthesize(QUESTIONS + [run.VoiceRunner.LONG])
    async with httpx.AsyncClient(timeout=60) as client:
        await run.SESSIONS.start(client)
        try:
            cases = [
                ("말소리", g, t, q)
                for g, t, q in product([0.1, 0.2, 0.3], [3.0, 6.0], QUESTIONS[:2])
            ]
            cases += [
                ("호출어", g, 5.0, q) for g, q in product([0.2, 0.5], QUESTIONS[:2])
            ]
            korean_wake = synth("헤이 자비스")
            for mode, gain, after, q in cases:
                await run.SESSIONS.new(keep_active=True)
                # 호출어 끼어들기는 실제처럼 호출어와 질문을 같은 목소리(한국어)로
                voice_wake = korean_wake if mode == "호출어" else wake
                runner = run.VoiceRunner(voice_wake, echo_gain=gain, barge_after=after)
                expect = {
                    "answer": ".",
                    "barge": mode == "말소리",
                    "wake_barge": mode == "호출어",
                }
                result = await runner.run({"input": q, "expect": expect})
                status = (
                    "pass"
                    if result["pass"]
                    else ("limit" if gain >= LIMIT_GAIN else "fail")
                )
                out.append(
                    {
                        "part": "C",
                        "kind": mode,
                        "gain": gain,
                        "user_at": after,
                        "question": q,
                        "status": status,
                        "note": result["note"],
                        "actual": result["actual"],
                    }
                )
                print(
                    "C", mode, gain, after, q, status, result["note"][:80], flush=True
                )
                await asyncio.sleep(2)
            for _ in range(6):
                await run.SESSIONS.new(keep_active=True)
                out.append(await stop_case(client, wake))
                await asyncio.sleep(2)
        finally:
            await run.SESSIONS.cleanup()
    return out


async def stop_case(client, wake: Path) -> dict:
    """긴 답을 듣다가 [중단] 을 누르면 3초 안에 대기로, 그 뒤로 답 음성이 안 온다."""
    import websockets

    r = run.redis_client()
    ps = r.pubsub()
    await ps.subscribe(STATE_CHANNEL, "edgevoice:tts:request")
    states, requests, audio_after = [], [], {"bytes": 0}
    stopped_at = None
    async with websockets.connect(run.GATEWAY_WS, max_size=None) as ws:

        async def drain():
            try:
                async for msg in ws:
                    if (
                        isinstance(msg, (bytes, bytearray))
                        and stopped_at
                        and time.perf_counter() - stopped_at > 1.0
                    ):
                        audio_after["bytes"] += len(msg)
            except Exception:
                pass

        task = asyncio.create_task(drain())

        async def send(audio):
            began = time.perf_counter()
            for n, i in enumerate(range(0, len(audio), 1600)):
                await ws.send(
                    (np.clip(audio[i : i + 1600], -1, 1) * 32767)
                    .astype(np.int16)
                    .tobytes()
                )
                pause = began + (n + 1) * 0.1 - time.perf_counter()
                if pause > 0:
                    await asyncio.sleep(pause)

        silence = np.zeros(1600 * 5)
        await send(
            np.concatenate(
                [
                    np.zeros(16000),
                    read16(wake),
                    np.zeros(19200),
                    read16(AUDIO / f"{run._audio_name(run.VoiceRunner.LONG)}.wav"),
                    np.zeros(16000),
                ]
            )
        )
        speaking = False
        for _ in range(200):
            m = await ps.get_message(ignore_subscribe_messages=True, timeout=0.1)
            if m and m["channel"].decode().endswith("tts:request"):
                speaking = True
                break
            await send(silence[:1600])
        await send(np.zeros(16000 * 2))  # 답을 2초쯤 듣다가
        stopped_at = time.perf_counter()
        response = await client.post(f"{run.BACKEND}/api/orchestrator/stop")
        ready_in = None
        for _ in range(60):
            await send(silence[:1600])
            m = await ps.get_message(ignore_subscribe_messages=True, timeout=0)
            while m:
                data = json.loads(m["data"])
                if m["channel"].decode().endswith("tts:request"):
                    requests.append(time.perf_counter() - stopped_at)
                elif data.get("new_state"):
                    states.append(data["new_state"])
                    if data["new_state"] == "READY" and ready_in is None:
                        ready_in = round(time.perf_counter() - stopped_at, 1)
                m = await ps.get_message(ignore_subscribe_messages=True, timeout=0)
        task.cancel()
    await r.aclose()
    late_requests = [t for t in requests if t > 1.0]
    ok = (
        response.status_code == 200
        and speaking
        and ready_in is not None
        and ready_in <= 3.0
        and not late_requests
        and audio_after["bytes"] == 0
    )
    note = (
        ""
        if ok
        else (
            f"대기까지 {ready_in}초 · 중단 뒤 새 문장 {len(late_requests)}개 · "
            f"중단 1초 뒤 받은 음성 {audio_after['bytes']}바이트"
        )
    )
    print("C stop", ok, note, flush=True)
    return {
        "part": "C",
        "kind": "중단 버튼",
        "status": "pass" if ok else "fail",
        "note": note,
        "actual": {"ready_in": ready_in, "states": states[-4:]},
    }


def save(parts: str, results: list) -> None:
    """이번에 돌린 부분만 바꿔 쓴다 — 부분마다 불러 도중에 멈춰도 남는다."""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    previous = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    keep = [x for x in previous if x["part"] not in parts]
    OUT.write_text(
        json.dumps(keep + results, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    from collections import Counter

    print(Counter((x["part"], x["status"]) for x in keep + results), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parts", default="ABC")
    args = parser.parse_args()
    if "A" in args.parts:
        save("A", part_a())
    if "B" in args.parts or "C" in args.parts:
        subprocess.run(
            ["taskkill", "/IM", "EdgeVoice.Agent.Desktop.exe", "/F"],
            capture_output=True,
        )  # 앱의 마이크 소리가 섞이지 않게
        try:
            if "B" in args.parts:
                save("B", asyncio.run(part_b()))
            if "C" in args.parts:
                save("C", asyncio.run(part_c()))
        finally:
            if run.APP.exists():
                subprocess.Popen([str(run.APP)], cwd=str(run.APP.parent))


if __name__ == "__main__":
    main()
