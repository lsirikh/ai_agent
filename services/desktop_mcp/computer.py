"""
컴퓨터 조작: 마우스·키보드 입력과 그림판에 그리기 (사용자 요청 2026-10-18).

실측: '그림판 열어서 강아지 그려 줘' 를 전혀 못 했다 — 마우스·키보드 도구가 없었다.
- 로컬 LLM 은 그릴 모양(원·타원·선·꺾은선·사각형·호)을 0~1000 캔버스 좌표로 정하고,
  여기서 그림판을 열어 흰 캔버스를 찾아 마우스로 그린다.
- 입력은 Windows SendInput(ctypes)으로 보낸다. 사용자 화면(로그인 세션)에서 돌아야 한다.
"""

import math
import time
from typing import Optional

import numpy as np

CANVAS_UNITS = 1000
CIRCLE_POINTS = 48
CANVAS_MARGIN = 0.04  # 캔버스 가장자리는 비워 둔다
PAINT_TITLES = ("그림판", "Paint")

_VK_NAMES = {
    "ctrl": 0x11, "control": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
}


def _number(shape: dict, key: str) -> float:
    return float(shape[key])


def _ellipse(cx: float, cy: float, rx: float, ry: float, start=0.0, end=360.0):
    steps = max(2, int(CIRCLE_POINTS * abs(end - start) / 360))
    points = []
    for i in range(steps + 1):
        angle = math.radians(start + (end - start) * i / steps)
        x, y = cx + rx * math.cos(angle), cy + ry * math.sin(angle)
        points.append((round(x), round(y)))
    return points


def shape_strokes(shape: dict) -> list:
    """모양 하나 → 마우스로 그을 선들(0~1000 좌표 점 목록). 모르는 모양은 []."""
    kind = str(shape.get("type", "")).lower()
    try:
        if kind == "circle":
            r = _number(shape, "r")
            return [_ellipse(_number(shape, "x"), _number(shape, "y"), r, r)]
        if kind == "ellipse":
            return [_ellipse(
                _number(shape, "x"), _number(shape, "y"),
                _number(shape, "rx"), _number(shape, "ry"),
            )]
        if kind == "arc":
            r = _number(shape, "r")
            return [_ellipse(
                _number(shape, "x"), _number(shape, "y"), r, r,
                _number(shape, "start"), _number(shape, "end"),
            )]
        if kind == "line":
            return [[
                (round(_number(shape, "x1")), round(_number(shape, "y1"))),
                (round(_number(shape, "x2")), round(_number(shape, "y2"))),
            ]]
        if kind == "rect":
            x, y = _number(shape, "x"), _number(shape, "y")
            w, h = _number(shape, "w"), _number(shape, "h")
            corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]
            return [[(round(a), round(b)) for a, b in corners]]
        if kind == "polyline":
            points = [(round(float(p[0])), round(float(p[1]))) for p in shape["points"]]
            return [points] if len(points) >= 2 else []
    except (KeyError, TypeError, ValueError, IndexError):
        return []
    return []


def to_screen(points, canvas) -> list:
    """0~1000 캔버스 좌표 → 화면 좌표 (canvas: 왼, 위, 오른, 아래)."""
    left, top, right, bottom = canvas
    width, height = right - left, bottom - top
    return [
        (
            round(left + width * min(max(x, 0), CANVAS_UNITS) / CANVAS_UNITS),
            round(top + height * min(max(y, 0), CANVAS_UNITS) / CANVAS_UNITS),
        )
        for x, y in points
    ]


def find_canvas(image: np.ndarray) -> Optional[tuple]:
    """그림판 화면에서 흰 캔버스 (왼, 위, 오른, 아래). 흰 줄·칸이 길게 이어진 곳."""
    white = np.all(image[:, :, :3] >= 250, axis=2)
    if not white.any():
        return None
    # 흰 칸이 세로로 긴 열(캔버스) → 그 열들이 거의 다 흰 행 → 그 행들이 거의 다 흰 열
    # (얇은 흰 도구 막대는 세로로 짧아 빠진다)
    cols = white.sum(axis=0)
    tall = np.where(cols >= 0.5 * cols.max())[0]
    ys = _longest_run(np.where(white[:, tall].sum(axis=1) >= 0.9 * len(tall))[0])
    if not len(ys):
        return None
    xs = _longest_run(np.where(white[ys].sum(axis=0) >= 0.9 * len(ys))[0])
    if not len(xs):
        return None
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def _longest_run(indices: np.ndarray) -> np.ndarray:
    """이어진 번호 중 가장 긴 구간(떨어진 흰 막대를 뺀다)."""
    if not len(indices):
        return indices
    runs = np.split(indices, np.where(np.diff(indices) != 1)[0] + 1)
    return max(runs, key=len)


def parse_keys(keys: str) -> list:
    """'ctrl+s' · 'alt+F4' · 'enter' → 가상 키 코드 목록."""
    codes = []
    for part in (keys or "").lower().replace(" ", "").split("+"):
        if part in _VK_NAMES:
            codes.append(_VK_NAMES[part])
        elif len(part) == 1 and part.isascii() and part.isalnum():
            codes.append(ord(part.upper()))
        elif part.startswith("f") and part[1:].isdigit() and 1 <= int(part[1:]) <= 24:
            codes.append(0x6F + int(part[1:]))
        else:
            raise ValueError(f"모르는 키: {part}")
    if not codes:
        raise ValueError("누를 키가 없습니다")
    return codes


def draw_picture(shapes: list, screen=None) -> str:
    """그림판을 열어 모양들을 그린다. screen: 화면 조작(시험용으로 바꿀 수 있다)."""
    strokes = [stroke for shape in shapes or [] for stroke in shape_strokes(shape)]
    if not strokes:
        raise ValueError(
            "그릴 모양이 없습니다. type 은 circle·ellipse·arc·line·rect·polyline"
        )
    screen = screen or WindowsScreen()
    canvas = screen.paint_canvas()
    for stroke in strokes:
        screen.drag(to_screen(stroke, canvas))
    return f"그림판에 선 {len(strokes)}개로 그렸습니다."


class WindowsScreen:
    """Windows 화면: 창 찾기·띄우기, 마우스·키보드 입력(SendInput)."""

    def __init__(self):
        import ctypes

        self.user32 = ctypes.windll.user32
        try:  # 화면 배율(DPI)과 상관없이 실제 픽셀 좌표를 쓴다
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

    # ── 창 ──────────────────────────────────────────────
    def find_window(self, titles) -> Optional[int]:
        import ctypes
        from ctypes import wintypes

        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def visit(hwnd, _):
            if self.user32.IsWindowVisible(hwnd):
                length = self.user32.GetWindowTextLengthW(hwnd)
                buffer = ctypes.create_unicode_buffer(length + 1)
                self.user32.GetWindowTextW(hwnd, buffer, length + 1)
                if any(buffer.value.endswith(t) or t in buffer.value for t in titles):
                    found.append(hwnd)
            return True

        self.user32.EnumWindows(visit, 0)
        return found[0] if found else None

    def focus(self, hwnd: int) -> None:
        self.user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
        self.user32.SetForegroundWindow(hwnd)
        time.sleep(0.8)

    def window_rect(self, hwnd: int) -> tuple:
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        self.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return rect.left, rect.top, rect.right, rect.bottom

    def paint_canvas(self) -> tuple:
        """그림판을 열고(없으면 실행) 최대화한 뒤 흰 캔버스의 그릴 영역."""
        import subprocess

        from PIL import ImageGrab

        hwnd = self.find_window(PAINT_TITLES)
        if hwnd is None:
            subprocess.Popen(["mspaint.exe"])
            for _ in range(40):
                time.sleep(0.25)
                hwnd = self.find_window(PAINT_TITLES)
                if hwnd:
                    break
        if hwnd is None:
            raise RuntimeError("그림판 창을 찾지 못했습니다")
        self.focus(hwnd)
        left, top, right, bottom = self.window_rect(hwnd)
        shot = np.asarray(
            ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
        )
        canvas = find_canvas(shot)
        if canvas is None:
            raise RuntimeError("그림판의 흰 캔버스를 찾지 못했습니다")
        cl, ct, cr, cb = canvas
        mx, my = (cr - cl) * CANVAS_MARGIN, (cb - ct) * CANVAS_MARGIN
        return (
            round(left + cl + mx), round(top + ct + my),
            round(left + cr - mx), round(top + cb - my),
        )

    # ── 마우스 ──────────────────────────────────────────
    def _mouse(self, flag: int) -> None:
        self.user32.mouse_event(flag, 0, 0, 0, 0)

    def move(self, x: int, y: int) -> None:
        self.user32.SetCursorPos(int(x), int(y))

    def click(self, x: int, y: int, button: str = "left", double: bool = False) -> None:
        down, up = (0x0008, 0x0010) if button == "right" else (0x0002, 0x0004)
        self.move(x, y)
        time.sleep(0.05)
        for _ in range(2 if double else 1):
            self._mouse(down)
            self._mouse(up)
            time.sleep(0.05)

    def drag(self, points) -> None:
        """점들을 따라 왼쪽 버튼을 누른 채 긋는다(사이를 촘촘히 채운다)."""
        if not points:
            return
        self.move(*points[0])
        time.sleep(0.03)
        self._mouse(0x0002)
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            steps = max(1, int(math.hypot(x1 - x0, y1 - y0) // 6))
            for i in range(1, steps + 1):
                self.move(x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps)
                time.sleep(0.004)
        self._mouse(0x0004)
        time.sleep(0.03)

    # ── 키보드 ──────────────────────────────────────────
    def _send_keys(self, events) -> None:
        import ctypes
        from ctypes import wintypes

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        class INPUT(ctypes.Structure):
            class _U(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]

            _anonymous_ = ("u",)
            _fields_ = [("type", wintypes.DWORD), ("u", _U)]

        for vk, scan, flags in events:
            item = INPUT(type=1)
            item.ki = KEYBDINPUT(vk, scan, flags, 0, None)
            self.user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(INPUT))
            time.sleep(0.01)

    def type_text(self, text: str) -> None:
        """글자를 그대로 입력한다(한글 포함, 입력기와 상관없이)."""
        unicode, key_up = 0x0004, 0x0002
        events = []
        for char in text:
            if char == "\n":
                events += [(0x0D, 0, 0), (0x0D, 0, key_up)]
                continue
            code = ord(char)
            events += [(0, code, unicode), (0, code, unicode | key_up)]
        self._send_keys(events)

    def press(self, codes) -> None:
        key_up = 0x0002
        self._send_keys(
            [(c, 0, 0) for c in codes] + [(c, 0, key_up) for c in reversed(codes)]
        )
