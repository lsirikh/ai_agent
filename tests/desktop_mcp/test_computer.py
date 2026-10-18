"""
컴퓨터 조작(마우스·키보드)과 그림판에 그리기 (사용자 요청 2026-10-18)

실측: '그림판 열어서 강아지 그려 줘' 를 전혀 못 했다 — 데스크톱 MCP 에 마우스·키보드
도구가 없었다(open_app · write_document · 파일 목록·읽기뿐).
→ 로컬 LLM 은 그릴 모양(원·타원·선·꺾은선·사각형·호)만 정하고, 서버가 그림판을 열어
  캔버스를 찾아 마우스로 그린다.
"""

import numpy as np
import pytest


def test_circle_becomes_closed_stroke_inside_canvas() -> None:
    from services.desktop_mcp.computer import shape_strokes

    (stroke,) = shape_strokes({"type": "circle", "x": 500, "y": 500, "r": 100})

    assert stroke[0] == stroke[-1]  # 닫힌 선
    assert len(stroke) >= 24
    xs, ys = zip(*stroke)
    assert 395 <= min(xs) and max(xs) <= 605 and 395 <= min(ys) and max(ys) <= 605


@pytest.mark.parametrize(
    "shape, points",
    [
        ({"type": "line", "x1": 0, "y1": 0, "x2": 1000, "y2": 1000}, 2),
        ({"type": "rect", "x": 100, "y": 100, "w": 200, "h": 50}, 5),
        ({"type": "polyline", "points": [[1, 2], [3, 4], [5, 6]]}, 3),
    ],
)
def test_simple_shapes(shape, points) -> None:
    from services.desktop_mcp.computer import shape_strokes

    (stroke,) = shape_strokes(shape)

    assert len(stroke) == points


def test_unknown_or_broken_shapes_are_skipped() -> None:
    from services.desktop_mcp.computer import shape_strokes

    assert shape_strokes({"type": "star"}) == []
    assert shape_strokes({"type": "circle", "x": "a"}) == []


def test_canvas_coordinates_map_to_screen() -> None:
    from services.desktop_mcp.computer import to_screen

    canvas = (100, 200, 1100, 700)  # 왼, 위, 오른, 아래

    assert to_screen([(0, 0), (1000, 1000), (500, 500)], canvas) == [
        (100, 200), (1100, 700), (600, 450),
    ]


def test_finds_white_canvas_in_paint_screenshot() -> None:
    from services.desktop_mcp.computer import find_canvas

    image = np.full((600, 800, 3), 243, dtype=np.uint8)  # 그림판 바탕(연회색)
    image[100:500, 150:650] = 255  # 흰 캔버스
    image[20:40, 10:790] = 255  # 위쪽 흰 도구 막대(얇다)

    assert find_canvas(image) == (150, 100, 650, 500)


def test_key_names_become_virtual_keys() -> None:
    from services.desktop_mcp.computer import parse_keys

    assert parse_keys("ctrl+s") == [0x11, ord("S")]
    assert parse_keys("Alt+F4") == [0x12, 0x73]
    assert parse_keys("enter") == [0x0D]
    with pytest.raises(ValueError):
        parse_keys("ctrl+없는키")


class FakeScreen:
    def __init__(self):
        self.drags = []

    def paint_canvas(self):
        return (100, 100, 1100, 600)

    def drag(self, points):
        self.drags.append(points)


def test_draw_picture_draws_each_shape_on_the_canvas() -> None:
    from services.desktop_mcp.computer import draw_picture

    screen = FakeScreen()
    shapes = [
        {"type": "circle", "x": 500, "y": 500, "r": 200},
        {"type": "line", "x1": 0, "y1": 0, "x2": 1000, "y2": 1000},
        {"type": "star"},
    ]

    message = draw_picture(shapes, screen=screen)

    assert len(screen.drags) == 2
    assert screen.drags[1] == [(100, 100), (1100, 600)]
    assert "2" in message


def test_draw_picture_needs_at_least_one_shape() -> None:
    from services.desktop_mcp.computer import draw_picture

    with pytest.raises(ValueError):
        draw_picture([{"type": "star"}], screen=FakeScreen())


def test_canvas_is_found_even_with_drawing_on_it() -> None:
    # 실측: 이미 그린 선이 지나는 열을 흰 칸으로 보지 않아 캔버스를 좁게 잡았다
    from services.desktop_mcp.computer import find_canvas

    image = np.full((600, 800, 3), 243, dtype=np.uint8)
    image[100:500, 150:650] = 255
    image[150:450, 300:302] = 0  # 세로 선
    image[300:302, 200:600] = 0  # 가로 선
    image[200:400, 400:500] = 0  # 칠한 곳

    assert find_canvas(image) == (150, 100, 650, 500)


def test_drawing_area_is_square_so_circles_stay_round() -> None:
    from services.desktop_mcp.computer import square_area

    assert square_area((100, 100, 1100, 600)) == (350, 100, 850, 600)
    assert square_area((0, 0, 400, 800)) == (0, 200, 400, 600)


@pytest.mark.parametrize(
    "title, usable",
    [
        ("제목 없음 - 그림판", True),
        ("Untitled - Paint", True),
        # 사용자가 연 그림 위에는 그리지 않는다(사용자 요청: 만든 것만 고친다)
        ("가족사진.png - 그림판", False),
        ("diagram.bmp - Paint", False),
        ("그림판 사용법 - Chrome", False),
    ],
)
def test_only_blank_paint_window_is_used(title, usable) -> None:
    from services.desktop_mcp.computer import is_blank_paint

    assert is_blank_paint(title) is usable
