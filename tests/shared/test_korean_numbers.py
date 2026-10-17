"""
TTS 숫자 읽기 (사용자 요청 2026-10-17)

'1시 20분' 은 '한 시 이십 분', '20도' 는 '이십 도'.
세는 말(시·개·명·살·시간…) 앞은 고유어(한·두·세),
분·도·년·월·일·원·% 앞은 한자어(일·이·삼).
"""

import pytest

from shared.korean_numbers import read_numbers


@pytest.mark.parametrize(
    "text, spoken",
    [
        ("지금은 1시 20분입니다.", "지금은 한 시 이십 분입니다."),
        ("오늘 기온은 20도예요.", "오늘 기온은 이십 도예요."),
        ("밤 10시 10분", "밤 열 시 십 분"),
        ("22시 07분", "이십이 시 칠 분"),
        ("12시 30분", "열두 시 삼십 분"),
        ("2026년 10월 17일", "이천이십육 년 시월 십칠 일"),
        ("2026 년 6 월 1 일", "이천이십육 년 유월 일 일"),
        ("사과 3개와 학생 21명", "사과 세 개와 학생 스물한 명"),
        ("20살 동생", "스무 살 동생"),
        ("1시간 30분 걸려요", "한 시간 삼십 분 걸려요"),
        ("1번째 항목과 2번째 항목", "첫 번째 항목과 두 번째 항목"),
        ("최고 24도·최저 12도", "최고 이십사 도·최저 십이 도"),
        ("기온 -15도", "기온 영하 십오 도"),
        ("18.4도", "십팔 점 사 도"),
        ("1,200,000원", "백이십만 원"),
        ("강수 확률 80%", "강수 확률 팔십 퍼센트"),
        ("바람 12km/h", "바람 십이 킬로미터"),
        ("25°C 이상", "이십오 도 이상"),
        ("1:20에 만나요", "한 시 이십 분에 만나요"),
        ("10000명", "만 명"),
        ("100000000원", "일억 원"),
    ],
)
def test_reads_numbers_the_korean_way(text, spoken) -> None:
    assert read_numbers(text) == spoken


@pytest.mark.parametrize("text", ["Qwen3.5 모델", "e37 요소", "mp3 파일"])
def test_leaves_numbers_inside_words_alone(text) -> None:
    assert read_numbers(text) == text


def test_voice_sentence_uses_korean_number_reading() -> None:
    from services.orchestrator.app.orchestrator import to_speech

    spoken, _ = to_speech("현재 시각은 **1시 20분**이고, 기온은 20도입니다.", None)

    assert spoken == "현재 시각은 한 시 이십 분이고, 기온은 이십 도입니다."
