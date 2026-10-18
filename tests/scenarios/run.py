"""
EdgeVoice 시나리오 실행·채점 (catalog.py 의 1000여 개).

    python tests/scenarios/run.py                 # 전부
    python tests/scenarios/run.py --kinds chat    # 일부 종류만
    python tests/scenarios/run.py --only S0001,S0002

결정적 시나리오는 코드를 바로 불러 채점하고, 실시간 시나리오는 돌고 있는 EdgeVoice
(백엔드 127.0.0.1:11000 · 게이트웨이 11008 · Redis 26379)와 로컬 LLM 으로 채점한다.
시험하느라 바꾼 설정은 끝나면 되돌리고, 지우는 것은 이번 실행이 만든 것뿐이다.
만드는 파일(결과·음성·보고)은 모두 Downloads/Tests/scenarios 아래에 둔다(사용자 요청).
원격 데스크톱이 끊겨 화면이 잠기면 화면을 쓰는 시나리오는 풀릴 때까지 기다린다.
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
import uuid
import wave
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog  # noqa: E402

BACKEND = "http://127.0.0.1:11000"
GATEWAY_WS = "ws://127.0.0.1:11008/ws/audio"
REDIS = ("127.0.0.1", 26379)
HOME_TESTS = Path.home() / "Downloads" / "Tests" / "scenarios"
OUT = HOME_TESTS / "results"
AUDIO = HOME_TESTS / "audio"
MARKER = "시나리오 시험"  # 이 실행이 지식 베이스에 넣는 것에는 모두 이 말을 넣는다
SCREEN_WAIT_SECONDS = 20 * 60
APP = (
    ROOT
    / "clients/dotnet/src/EdgeVoice.Agent.Desktop/bin/Debug/net8.0"
    / "EdgeVoice.Agent.Desktop.exe"
)
CHAT_CONCURRENCY = 3


def _result(ok: bool, actual, note: str = "") -> dict:
    return {"pass": bool(ok), "actual": actual, "note": note}


# ── 결정적 ──────────────────────────────────────────────────
def run_deterministic(s: dict) -> dict:
    kind, given, expect = s["kind"], s["input"], s["expect"]
    if kind == "route":
        from shared.tools import required_tools

        got = required_tools(given, catalog.OFFERED)
        return _result(got == expect, got)
    if kind == "cannot":
        from shared.tools import unavailable_action_reply

        got = unavailable_action_reply(given, expect["offered"])
        return _result((got is not None) == expect["refuse"], got)
    if kind == "numbers":
        from shared.korean_numbers import read_numbers

        got = read_numbers(given)
        return _result(got == expect, got)
    if kind == "speech":
        from services.orchestrator.app.orchestrator import to_speech

        got, _ = to_speech(given, None)
        return _result(got == expect, got)
    if kind == "confirm":
        from services.orchestrator.app.orchestrator import NO_PATTERN, YES_PATTERN

        got = (
            "no"
            if NO_PATTERN.search(given)
            else "yes"
            if YES_PATTERN.search(given)
            else "none"
        )
        return _result(got == expect, got)
    if kind == "wake":
        from services.orchestrator.app.orchestrator import strip_wake_phrase

        got = strip_wake_phrase(given)
        return _result(got == expect, got)
    if kind == "url":
        from shared.browser_assist import normalize_url

        got = normalize_url(given)
        return _result(got == expect, got)
    if kind == "ssrf":
        from shared.tools import UnsafeURLError, check_url

        async def resolve(host, port):
            fixed = {
                "www.naver.com": "223.130.200.104",
                "example.com": "93.184.216.34",
                "www.google.com": "142.250.196.100",
                "github.com": "20.200.245.247",
            }
            if host in fixed:
                return [fixed[host]]
            if host == "intranet":
                return ["10.1.2.3"]
            return ["10.0.0.1"]

        try:
            asyncio.run(check_url(given, resolve=resolve))
            got = "allowed"
        except UnsafeURLError as e:
            got = "blocked"
            return _result(got == expect, f"{got}: {e}")
        return _result(got == expect, got)
    if kind == "han":
        sys.path.insert(0, str(ROOT / "services/llm"))
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "han_tokens", ROOT / "services/llm/edgevoice_guard/han_tokens.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        got = module.is_banned_text(given)
        return _result(got == expect, got)
    raise ValueError(kind)


# ── 실시간: 채팅 ────────────────────────────────────────────
async def chat_once(
    client, message: str, session_id: str, use_rag: bool = False
) -> dict:
    """채팅 한 턴: 답·도구 호출·도구 결과를 모은다(확인이 필요한 도구는 승인)."""
    text, tools, results, errors = "", [], [], []
    body = {"message": message, "use_rag": use_rag, "session_id": session_id}
    async with client.stream(
        "POST", f"{BACKEND}/api/chat/message", json=body, timeout=300
    ) as response:
        async for line in response.aiter_lines():
            if not line.startswith("data:"):
                continue
            try:
                event = json.loads(line[5:])
            except ValueError:
                continue
            kind = event.get("type")
            if kind == "token":
                text += event.get("content") or ""
            elif kind in ("tool_call", "tool_confirm"):
                tools.append(str(event.get("tool", "")).split("__")[-1])
                if kind == "tool_confirm":
                    await client.post(
                        f"{BACKEND}/api/chat/confirm",
                        json={"confirm_id": event.get("id"), "approved": True},
                        timeout=30,
                    )
            elif kind == "tool_result":
                results.append(
                    {
                        "tool": str(event.get("tool", "")).split("__")[-1],
                        "error": bool(event.get("is_error")),
                        "content": str(event.get("content") or "")[:400],
                    }
                )
            elif kind == "error":
                errors.append(
                    event.get("message") or event.get("content") or str(event)
                )
    return {"text": text.strip(), "tools": tools, "results": results, "errors": errors}


def judge_chat(expect: dict, turn: dict) -> tuple:
    problems = []
    text, tools = turn["text"], turn["tools"]
    if turn["errors"]:
        problems.append(f"오류: {turn['errors'][0]}")
    if not text:
        problems.append("답이 비었다")
    if expect.get("tools_none") and tools:
        problems.append(f"도구를 쓰면 안 됨: {tools}")
    if expect.get("tools_any") and not set(expect["tools_any"]) & set(tools):
        problems.append(f"{expect['tools_any']} 중 하나를 써야 함 (쓴 것: {tools})")
    if expect.get("tools_all") and not set(expect["tools_all"]) <= set(tools):
        problems.append(f"{expect['tools_all']} 를 모두 써야 함 (쓴 것: {tools})")
    for pattern in expect.get("must", []):
        if not re.search(pattern, text):
            problems.append(f"답에 /{pattern}/ 가 없다")
    for pattern in expect.get("must_not", []) + [catalog.HAN]:
        found = re.search(pattern, text)
        if found:
            problems.append(f"답에 /{pattern}/ 가 있다: '{found.group(0)}'")
    if expect.get("min_len") and len(text) < expect["min_len"]:
        problems.append("답이 너무 짧다")
    joined = " ".join(r["content"] for r in turn["results"] if not r["error"])
    for needle in expect.get("result_has", []):
        if needle not in joined:
            problems.append(f"도구 결과에 '{needle}' 가 없다")
    return not problems, "; ".join(problems)


async def run_chat(s: dict, client) -> dict:
    session = str(uuid.uuid4())
    for earlier in s["expect"].get("history", []):
        await chat_once(client, earlier, session)
    turn = await chat_once(client, s["input"], session)
    ok, note = judge_chat(s["expect"], turn)
    return _result(
        ok,
        {
            "text": turn["text"][:600],
            "tools": turn["tools"],
            "results": turn["results"][:4],
        },
        note,
    )


# ── 실시간: 그림판 잉크 확인 ────────────────────────────────
def paint_ink() -> int:
    """그림판 캔버스의 어두운 점 수."""
    import numpy as np
    from PIL import ImageGrab

    from services.desktop_mcp import computer

    screen = computer.WindowsScreen()
    hwnd = screen.find_blank_paint()
    if not hwnd:
        return 0
    left, top, right, bottom = screen.window_rect(hwnd)
    shot = np.asarray(ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True))
    canvas = computer.find_canvas(shot)
    if not canvas:
        return 0
    cl, ct, cr, cb = canvas
    area = shot[ct:cb, cl:cr, :3]
    return int((area.max(axis=2) < 120).sum())


def clear_paint() -> None:
    from services.desktop_mcp import computer

    screen = computer.WindowsScreen()
    hwnd = screen.find_blank_paint()  # 시험이 연 새 그림판만 비운다
    if hwnd:
        screen.focus(hwnd)
        screen.press(computer.parse_keys("ctrl+a"))
        time.sleep(0.3)
        screen.press(computer.parse_keys("delete"))
        time.sleep(0.3)


def screen_ready() -> bool:
    """화면을 찍을 수 있는지(원격 데스크톱이 끊기면 잠겨 실패한다)."""
    try:
        from PIL import ImageGrab

        ImageGrab.grab(bbox=(0, 0, 8, 8))
        return True
    except OSError:
        return False


async def wait_for_screen() -> bool:
    """화면이 풀릴 때까지 기다린다(최대 SCREEN_WAIT_SECONDS)."""
    deadline = time.time() + SCREEN_WAIT_SECONDS
    while not screen_ready():
        if time.time() > deadline:
            return False
        await asyncio.sleep(15)
    return True


def skipped(reason: str) -> dict:
    return {"pass": None, "actual": None, "note": reason}


async def run_desktop(s: dict, client) -> dict:
    if not await wait_for_screen():
        return skipped("화면이 잠겨 있어 건너뜀(원격 데스크톱 끊김)")
    ink_check = s["expect"].get("canvas_ink")
    if ink_check:
        clear_paint()
    result = await run_chat(s, client)
    if ink_check:
        ink = paint_ink()
        result["actual"]["ink"] = ink
        if ink < 200:
            result["pass"] = False
            result["note"] = (
                result["note"] + "; " if result["note"] else ""
            ) + f"캔버스에 그린 선이 거의 없다(어두운 점 {ink}개)"
    return result


# ── 실시간: 설정 ────────────────────────────────────────────
class SettingsRunner:
    def __init__(self, client):
        self.client = client
        self.saved_skills = None
        self.saved_general = None

    async def get(self, path):
        response = await self.client.get(f"{BACKEND}{path}", timeout=60)
        return response.status_code, response.json()

    async def put(self, path, body):
        response = await self.client.put(f"{BACKEND}{path}", json=body, timeout=120)
        return response.status_code, (response.json() if response.content else None)

    async def server(self, name):
        _, data = await self.get("/api/settings/mcp")
        return next((x for x in data["servers"] if x["name"] == name), None)

    async def set_desktop(self, enabled: bool):
        server = await self.server("desktop")
        body = {
            k: server[k]
            for k in (
                "name",
                "url",
                "command",
                "args",
                "env",
                "allowed_tools",
                "trusted",
                "always_confirm",
                "no_confirm",
                "timeout",
            )
        }
        body["enabled"] = enabled
        return await self.put("/api/settings/mcp/desktop", body)

    async def skills(self, disabled=None, prompts=None):
        _, current = await self.get("/api/settings/skills")
        body = {
            "disabled_tools": current["disabled_tools"]
            if disabled is None
            else disabled,
            "prompts": current["prompts"] if prompts is None else prompts,
        }
        return await self.put("/api/settings/skills", body)

    async def ask(self, message):
        return await chat_once(self.client, message, str(uuid.uuid4()))

    async def step(self, name: str) -> tuple:
        if self.saved_skills is None:
            _, skills = await self.get("/api/settings/skills")
            self.saved_skills = {
                "disabled_tools": skills["disabled_tools"],
                "prompts": skills["prompts"],
            }
        if name == "mcp_list":
            _, data = await self.get("/api/settings/mcp")
            status = {x["name"]: x["status"] for x in data["servers"]}
            return status.get("browser") == "connected" and status.get(
                "desktop"
            ) == "connected", status
        if name == "mcp_disable_desktop":
            code, _ = await self.set_desktop(False)
            server = await self.server("desktop")
            return code == 200 and not server["enabled"], {
                "code": code,
                "status": server["status"],
            }
        if name == "mcp_disabled_refuses":
            turn = await self.ask("메모장 열어줘")
            ok = not any(
                t in ("open_app", "write_document") for t in turn["tools"]
            ) and bool(re.search(r"없|못|불가|연결", turn["text"]))
            return ok, {"text": turn["text"][:200], "tools": turn["tools"]}
        if name == "mcp_enable_desktop":
            code, _ = await self.set_desktop(True)
            for _ in range(20):
                server = await self.server("desktop")
                if server["status"] == "connected":
                    break
                await asyncio.sleep(1)
            return code == 200 and server["status"] == "connected", {
                "status": server["status"]
            }
        if name == "mcp_reenabled_draws":
            if not await wait_for_screen():
                return None, "화면이 잠겨 있어 건너뜀(원격 데스크톱 끊김)"
            clear_paint()
            turn = await self.ask("그림판에 웃는 얼굴 그려줘")
            return "draw_picture" in turn["tools"], {
                "tools": turn["tools"],
                "ink": paint_ink(),
            }
        if name == "mcp_bad_name":
            response = await self.client.post(
                f"{BACKEND}/api/settings/mcp", json={"name": "", "url": "http://x"}
            )
            return response.status_code == 422, response.status_code
        if name == "mcp_missing":
            code, _ = await self.put(
                "/api/settings/mcp/nope-not-here",
                {"name": "nope-not-here", "url": "http://x"},
            )
            return code == 404, code
        if name == "mcp_add_delete":
            body = {
                "name": "scenario-test",
                "url": "http://127.0.0.1:9/mcp",
                "enabled": False,
            }
            added = await self.client.post(
                f"{BACKEND}/api/settings/mcp", json=body, timeout=60
            )
            listed = await self.server("scenario-test") is not None
            removed = await self.client.delete(
                f"{BACKEND}/api/settings/mcp/scenario-test", timeout=60
            )
            gone = await self.server("scenario-test") is None
            return (
                added.status_code == 200
                and listed
                and removed.status_code == 200
                and gone,
                {
                    "add": added.status_code,
                    "listed": listed,
                    "delete": removed.status_code,
                },
            )
        if name == "skills_list":
            _, data = await self.get("/api/settings/skills")
            names = [b["name"] for b in data["builtin"]]
            return len(names) == 5, names
        if name == "skill_weather_off":
            await self.skills(disabled=["get_weather"])
            turn = await self.ask("서울 날씨 어때?")
            return "get_weather" not in turn["tools"], {
                "tools": turn["tools"],
                "text": turn["text"][:200],
            }
        if name == "skill_weather_on":
            await self.skills(disabled=[])
            turn = await self.ask("서울 날씨 어때?")
            return "get_weather" in turn["tools"], {"tools": turn["tools"]}
        if name == "skill_prompt_add":
            prompt = {
                "name": "scenario-dog",
                "description": "시험",
                "instructions": "모든 답의 맨 끝에 반드시 '멍멍!' 이라고 붙인다.",
                "enabled": True,
            }
            await self.skills(prompts=self.saved_skills["prompts"] + [prompt])
            turn = await self.ask("안녕")
            return "멍멍" in turn["text"], {"text": turn["text"][:200]}
        if name == "skill_prompt_off":
            prompt = {
                "name": "scenario-dog",
                "description": "시험",
                "instructions": "모든 답의 맨 끝에 반드시 '멍멍!' 이라고 붙인다.",
                "enabled": False,
            }
            await self.skills(prompts=self.saved_skills["prompts"] + [prompt])
            turn = await self.ask("안녕")
            return "멍멍" not in turn["text"], {"text": turn["text"][:200]}
        if name == "skill_prompt_delete":
            await self.skills(prompts=self.saved_skills["prompts"])
            _, data = await self.get("/api/settings/skills")
            return all(p["name"] != "scenario-dog" for p in data["prompts"]), data[
                "prompts"
            ]
        if name == "skill_search_off":
            await self.skills(disabled=["web_search"])
            turn = await self.ask("원당시장 어디 있어?")
            return "web_search" not in turn["tools"], {"tools": turn["tools"]}
        if name == "skill_search_on":
            await self.skills(disabled=self.saved_skills["disabled_tools"])
            turn = await self.ask("원당시장 어디 있어?")
            return "web_search" in turn["tools"], {"tools": turn["tools"]}
        if name == "general_roundtrip":
            _, general = await self.get("/api/settings/general")
            self.saved_general = {
                k: general[k]
                for k in (
                    "wake_word",
                    "language",
                    "voice_speed",
                    "wake_word_threshold",
                    "end_pause_seconds",
                    "listening_timeout_seconds",
                )
            }
            code, _ = await self.put("/api/settings/general", self.saved_general)
            _, again = await self.get("/api/settings/general")
            same = all(again[k] == v for k, v in self.saved_general.items())
            return code == 200 and same, again
        if name == "general_resync":
            changed = {**self.saved_general, "wake_word_threshold": 0.31}
            await self.put("/api/settings/general", changed)
            subprocess.run(["docker", "restart", "ev-wake-word"], capture_output=True)
            threshold = None
            for _ in range(40):
                await asyncio.sleep(1.5)
                try:
                    info = (
                        await self.client.get("http://127.0.0.1:11005/info", timeout=5)
                    ).json()
                    threshold = info["settings"]["threshold"]
                    if abs(threshold - 0.31) < 1e-6:
                        break
                except Exception:
                    continue
            await self.put("/api/settings/general", self.saved_general)
            return threshold is not None and abs(threshold - 0.31) < 1e-6, {
                "threshold": threshold
            }
        raise ValueError(name)

    async def restore(self):
        if self.saved_skills is not None:
            await self.put("/api/settings/skills", self.saved_skills)
        server = await self.server("desktop")
        if server and not server["enabled"]:
            await self.set_desktop(True)
        if await self.server("scenario-test"):
            await self.client.delete(f"{BACKEND}/api/settings/mcp/scenario-test")
        if self.saved_general:
            await self.put("/api/settings/general", self.saved_general)


# ── 실시간: 지식 베이스 ─────────────────────────────────────
class KnowledgeRunner:
    FACT = (
        f"EdgeVoice {MARKER} 문서. 파란우체통 주식회사의 대표는 홍길순이다. "
        "파란우체통 주식회사는 2019년에 세워졌고 본사는 고양시에 있다."
    )

    def __init__(self, client):
        self.client = client
        self.started = time.time()
        self.doc_ids = []

    async def step(self, name: str) -> tuple:
        if name == "upload":
            files = {
                "file": ("scenario_kb.txt", self.FACT.encode("utf-8"), "text/plain")
            }
            response = await self.client.post(
                f"{BACKEND}/api/knowledge/upload",
                files=files,
                data={"title": "시나리오 시험 문서"},
                timeout=120,
            )
            body = response.json()
            if response.status_code == 200:
                self.doc_ids.append(body["doc_id"])
            return response.status_code == 200, body
        if name == "search":
            response = await self.client.post(
                f"{BACKEND}/api/knowledge/search",
                json={"query": "파란우체통 대표"},
                timeout=60,
            )
            text = json.dumps(response.json(), ensure_ascii=False)
            return "홍길순" in text, text[:300]
        if name == "ask":
            turn = await chat_once(
                self.client,
                "파란우체통 주식회사 대표가 누구야?",
                str(uuid.uuid4()),
                use_rag=True,
            )
            return "홍길순" in turn["text"], turn["text"][:300]
        if name == "learn":
            turn = await chat_once(
                self.client,
                f"기억해: {MARKER}용 비밀 단어는 '보라색 기린'이야",
                str(uuid.uuid4()),
            )
            return "learn_note" in turn["tools"], {
                "tools": turn["tools"],
                "text": turn["text"][:200],
            }
        if name == "recall":
            await asyncio.sleep(3)
            turn = await chat_once(
                self.client,
                f"{MARKER}용 비밀 단어가 뭐였지?",
                str(uuid.uuid4()),
                use_rag=True,
            )
            return "기린" in turn["text"], turn["text"][:300]
        if name == "cleanup":
            return await self.cleanup()
        raise ValueError(name)

    async def cleanup(self) -> tuple:
        """이번 실행이 만든 문서만 지운다: 올린 문서 + 실행 뒤에 생긴 시험 표시 문서."""
        from datetime import datetime

        response = await self.client.get(
            f"{BACKEND}/api/knowledge/documents", timeout=60
        )
        docs = response.json()
        docs = docs.get("documents", docs) if isinstance(docs, dict) else docs
        removed = []
        for doc in docs:
            mine = doc.get("doc_id") in self.doc_ids
            try:
                made = (
                    datetime.fromisoformat(doc["uploaded_at"]).timestamp()
                    >= self.started
                )
            except (KeyError, ValueError):
                made = False
            label = json.dumps(doc, ensure_ascii=False)
            if mine or (made and (MARKER in label or "보라색 기린" in label)):
                await self.client.delete(
                    f"{BACKEND}/api/knowledge/documents/{doc['doc_id']}"
                )
                removed.append(
                    {"doc_id": doc["doc_id"], "filename": doc.get("filename")}
                )
        return bool(removed), {"removed": removed}


# ── 실시간: 음성 ────────────────────────────────────────────
def synthesize(texts: list) -> None:
    """한국어 음성(Windows 'Heami')으로 질문 WAV 를 만든다(없는 것만)."""
    AUDIO.mkdir(parents=True, exist_ok=True)
    missing = [
        t for t in texts if not (AUDIO / f"{abs(hash(t)) % 10**10}.wav").exists()
    ]
    if not missing:
        return
    lines = [
        "Add-Type -AssemblyName System.Speech",
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer",
        "$v = $s.GetInstalledVoices() | ? { $_.VoiceInfo.Culture.Name -eq 'ko-KR' }"
        " | select -First 1",
        "$s.SelectVoice($v.VoiceInfo.Name)",
        "$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, "
        "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, "
        "[System.Speech.AudioFormat.AudioChannel]::Mono)",
    ]
    for text in missing:
        path = AUDIO / f"{abs(hash(text)) % 10**10}.wav"
        quoted = text.replace("'", "''")
        lines.append(f"$s.SetOutputToWaveFile('{path}', $f); $s.Speak('{quoted}')")
    lines.append("$s.SetOutputToNull()")
    script = AUDIO / "synth.ps1"
    script.write_text("\n".join(lines), encoding="utf-8-sig")
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


def wav_of(text: str):
    import numpy as np

    with wave.open(str(AUDIO / f"{abs(hash(text)) % 10**10}.wav"), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


def _norm(text: str) -> str:
    return re.sub(r"[\s.,?!~'\"]", "", text or "")


class VoiceRunner:
    LONG = "한국의 사계절에 대해 자세히 설명해줘"
    BACKGROUND = "어제 뉴스에서는 내일 전국에 비가 온다고 했고 주말에는 맑겠다고 합니다"

    def __init__(self, wake_wav: Path):
        import numpy as np

        with wave.open(str(wake_wav), "rb") as w:
            self.wake = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)

    async def run(self, s: dict) -> dict:
        import numpy as np
        import redis.asyncio as aioredis
        import websockets

        expect = s["expect"]
        r = aioredis.Redis(host=REDIS[0], port=REDIS[1])
        ps = r.pubsub()
        await ps.subscribe(
            "edgevoice:stt:result",
            "edgevoice:orchestrator:state",
            "edgevoice:tts:request",
            "edgevoice:barge_in:detected",
            "edgevoice:wake_word:detected",
        )
        t0 = time.perf_counter()
        events, echo, speaking, ready_after_answer = (
            [],
            [],
            asyncio.Event(),
            asyncio.Event(),
        )
        stop = asyncio.Event()

        async def listen():
            while not stop.is_set():
                m = await ps.get_message(ignore_subscribe_messages=True, timeout=0.2)
                if not m:
                    continue
                ch = m["channel"].decode().removeprefix("edgevoice:")
                data = json.loads(m["data"])
                events.append(
                    {"t": round(time.perf_counter() - t0, 2), "ch": ch, "d": data}
                )
                if ch == "tts:request":
                    speaking.set()
                if ch == "orchestrator:state":
                    if data.get("new_state") == "LISTENING":
                        echo.clear()  # 앱처럼 남은 답 음성을 버린다
                    if data.get("new_state") == "READY":
                        ready_after_answer.set()

        listener = asyncio.create_task(listen())
        try:
            async with websockets.connect(GATEWAY_WS, max_size=None) as ws:

                async def drain():
                    try:
                        async for msg in ws:
                            if isinstance(msg, (bytes, bytearray)) and len(msg) >= 4:
                                f = np.frombuffer(
                                    bytes(msg)[: len(msg) // 4 * 4], dtype=np.float32
                                )
                                x = np.interp(
                                    np.arange(0, len(f), 1.5), np.arange(len(f)), f
                                )
                                echo.extend(
                                    (np.clip(x * 0.2, -1, 1) * 32767)
                                    .astype(np.int16)
                                    .tolist()
                                )
                    except Exception:
                        pass

                drainer = asyncio.create_task(drain())

                async def stream(audio, seconds_cap=None):
                    start = time.perf_counter()
                    for n, i in enumerate(range(0, len(audio), 1600)):
                        chunk = audio[i : i + 1600].astype(np.int32)
                        k = min(len(echo), len(chunk))
                        if k:
                            chunk[:k] += np.array(echo[:k], dtype=np.int32)
                            del echo[:k]
                        await ws.send(
                            np.clip(chunk, -32768, 32767).astype(np.int16).tobytes()
                        )
                        delay = start + (n + 1) * 0.1 - time.perf_counter()
                        if delay > 0:
                            await asyncio.sleep(delay)

                def sil(sec):
                    return np.zeros(int(16000 * sec), dtype=np.int16)

                await stream(np.concatenate([sil(1.0), self.wake, sil(1.2)]))
                if expect.get("silent"):
                    await stream(sil(9.0))
                elif expect.get("barge") or expect.get("wake_barge"):
                    await stream(np.concatenate([wav_of(self.LONG), sil(1.0)]))
                    for _ in range(300):
                        if speaking.is_set():
                            break
                        await stream(sil(0.1))
                    await stream(sil(2.5))
                    ready_after_answer.clear()
                    second = wav_of(s["input"])
                    if expect.get("wake_barge"):
                        second = np.concatenate([self.wake, sil(0.8), second])
                    await stream(np.concatenate([second, sil(1.0)]))
                else:
                    tail = (
                        wav_of(self.BACKGROUND) // 5
                        if expect.get("background")
                        else sil(0.1)
                    )
                    await stream(np.concatenate([wav_of(s["input"]), sil(0.4), tail]))
                    ready_after_answer.clear() if not expect.get("background") else None
                deadline = time.perf_counter() + 70
                while (
                    time.perf_counter() < deadline and not ready_after_answer.is_set()
                ):
                    await stream(sil(0.5))
                await stream(sil(1.0))
                drainer.cancel()
        finally:
            stop.set()
            await listener
            await r.aclose()
        return self.judge(s, events)

    def judge(self, s: dict, events: list) -> dict:
        expect = s["expect"]
        stt = [e["d"].get("text", "") for e in events if e["ch"] == "stt:result"]
        tts = [e["d"].get("text", "") for e in events if e["ch"] == "tts:request"]
        barges = [
            e["d"].get("source") for e in events if e["ch"] == "barge_in:detected"
        ]
        wakes = [e for e in events if e["ch"] == "wake_word:detected"]
        states = [
            e["d"].get("new_state") for e in events if e["ch"] == "orchestrator:state"
        ]
        actual = {
            "stt": stt,
            "tts": [t[:80] for t in tts[:6]],
            "barge_in": barges,
            "wake": len(wakes),
            "last_state": states[-1] if states else None,
        }
        problems = []
        if not wakes:
            problems.append("호출어를 듣지 못했다")
        if expect.get("silent"):
            if any(_norm(t) for t in stt):
                problems.append(f"말이 없는데 받아 적었다: {stt}")
            if states and states[-1] not in ("READY", "IDLE"):
                problems.append(f"대기로 돌아가지 않았다: {states[-1]}")
            return _result(not problems, actual, "; ".join(problems))
        target = _norm(s["input"])
        heard = [_norm(t) for t in stt]
        best = max((SequenceMatcher(None, target, h).ratio() for h in heard), default=0)
        actual["similarity"] = round(best, 2)
        if best < 0.6:
            problems.append(f"질문을 제대로 받아 적지 못했다(유사도 {best:.2f})")
        if expect.get("barge") and "speech" not in barges:
            problems.append("호출어 없이 말해도 끊지 않았다")
        if expect.get("wake_barge") and len(wakes) < 2:
            problems.append("답하는 도중 호출어로 끊지 못했다")
        if expect.get("background"):
            if any("뉴스" in t or "주말" in t for t in stt):
                problems.append("질문 뒤 배경 말소리까지 받아 적었다")
        answer = " ".join(tts)
        if not tts:
            problems.append("답을 말하지 않았다")
        elif not re.search(expect.get("answer", "."), answer):
            problems.append(f"답에 /{expect['answer']}/ 가 없다")
        if re.search(catalog.HAN, answer):
            problems.append("답에 한자·가나가 있다")
        return _result(not problems, actual, "; ".join(problems))


# ── 실행 ────────────────────────────────────────────────────
LIVE_ORDER = ["chat", "settings", "knowledge", "browser", "desktop", "voice"]


async def run_live(items: list, results: dict, save) -> None:
    import httpx

    by_kind = {k: [s for s in items if s["kind"] == k] for k in LIVE_ORDER}
    async with httpx.AsyncClient(timeout=300) as client:
        semaphore = asyncio.Semaphore(CHAT_CONCURRENCY)

        async def one_chat(s):
            async with semaphore:
                started = time.perf_counter()
                try:
                    results[s["id"]] = await run_chat(s, client)
                except Exception as e:
                    results[s["id"]] = _result(False, None, f"예외: {e!r}")
                results[s["id"]]["seconds"] = round(time.perf_counter() - started, 1)
                save()

        await asyncio.gather(*(one_chat(s) for s in by_kind["chat"]))

        for kind, runner in (
            ("settings", SettingsRunner(client)),
            ("knowledge", KnowledgeRunner(client)),
        ):
            try:
                for s in by_kind[kind]:
                    started = time.perf_counter()
                    try:
                        ok, actual = await runner.step(s["input"])
                        results[s["id"]] = (
                            skipped(actual) if ok is None else _result(ok, actual)
                        )
                    except Exception as e:
                        results[s["id"]] = _result(False, None, f"예외: {e!r}")
                    results[s["id"]]["seconds"] = round(
                        time.perf_counter() - started, 1
                    )
                    save()
            finally:
                if kind == "settings":
                    await runner.restore()
                else:
                    await runner.cleanup()

        for s in by_kind["browser"] + by_kind["desktop"]:
            started = time.perf_counter()
            try:
                run = run_desktop if s["kind"] == "desktop" else run_chat
                results[s["id"]] = await run(s, client)
            except Exception as e:
                results[s["id"]] = _result(False, None, f"예외: {e!r}")
            results[s["id"]]["seconds"] = round(time.perf_counter() - started, 1)
            save()

    if by_kind["voice"]:
        voice_items = by_kind["voice"]
        synthesize(
            [s["input"] for s in voice_items if s["input"]]
            + [VoiceRunner.LONG, VoiceRunner.BACKGROUND]
        )
        subprocess.run(
            ["taskkill", "/IM", "EdgeVoice.Agent.Desktop.exe", "/F"],
            capture_output=True,
        )  # 앱의 마이크 소리가 섞이지 않게
        runner = VoiceRunner(
            Path(os.environ.get("SCENARIO_WAKE_WAV", AUDIO / "wake.wav"))
        )
        try:
            for s in voice_items:
                started = time.perf_counter()
                try:
                    results[s["id"]] = await runner.run(s)
                except Exception as e:
                    results[s["id"]] = _result(False, None, f"예외: {e!r}")
                results[s["id"]]["seconds"] = round(time.perf_counter() - started, 1)
                save()
                await asyncio.sleep(2)
        finally:
            if APP.exists():
                subprocess.Popen([str(APP)], cwd=str(APP.parent))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kinds", default="")
    parser.add_argument("--only", default="")
    parser.add_argument("--out", default=str(OUT / "latest.json"))
    parser.add_argument(
        "--resume", action="store_true", help="이미 채점한 것은 건너뛴다"
    )
    args = parser.parse_args()

    items = catalog.all_scenarios()
    if args.kinds:
        items = [s for s in items if s["kind"] in args.kinds.split(",")]
    if args.only:
        items = [s for s in items if s["id"] in args.only.split(",")]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    results = {}
    if args.resume and out.exists():
        results = {
            k: v
            for k, v in json.loads(out.read_text(encoding="utf-8"))["results"].items()
        }
        items = [s for s in items if s["id"] not in results]

    def save():
        out.write_text(
            json.dumps(
                {"saved_at": time.strftime("%Y-%m-%d %H:%M:%S"), "results": results},
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )

    live_kinds = set(LIVE_ORDER)
    for s in items:
        if s["kind"] not in live_kinds:
            try:
                results[s["id"]] = run_deterministic(s)
            except Exception as e:
                results[s["id"]] = _result(False, None, f"예외: {e!r}")
    save()
    asyncio.run(run_live([s for s in items if s["kind"] in live_kinds], results, save))
    save()
    passed = sum(1 for r in results.values() if r["pass"])
    skips = sum(1 for r in results.values() if r["pass"] is None)
    print(f"{passed}/{len(results)} 통과 · 건너뜀 {skips} → {out}")


if __name__ == "__main__":
    main()
