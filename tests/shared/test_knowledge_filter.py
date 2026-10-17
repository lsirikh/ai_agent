"""
지식 근거 거르기 테스트 (실측 기반)

점수만으로는 무관한 질문(0.49~0.56)과 관련 질문(0.53~0.70)이 겹쳐,
"오늘 날씨 알려줘" 에 GOP API 문서의 weather_mode(SEA_FOG) 조각이 붙어
"해무" 라고 답했다.
애매한 점수 구간에서는 질문의 핵심 단어가 조각에 실제로 있을 때만 근거로 쓴다.
"""

import pytest

GOP_JSON_CHUNK = (
    '# 안개\n    SEA_FOG = "SEA_FOG"   # 해무\n"weather_mode": 2, "day_night": 1'
)
DRAMA_CHUNK = (
    "해솔시 골목의 오래된 옷 수선집을 물려받은 주인공 차은별이 손님들의 사연을 수선하며"
)
SINGER_CHUNK = (
    "윤하람은 대한민국의 가상 싱어송라이터이다. 소속사는 파란별엔터테인먼트이며"
)


@pytest.mark.parametrize(
    "query, chunk, score, expected",
    [
        ("오늘 날씨 알려줘", GOP_JSON_CHUNK, 0.56, False),
        ("지금 몇 시야?", GOP_JSON_CHUNK, 0.513, False),
        ("파이썬 리스트 정렬하는 법 알려줘", GOP_JSON_CHUNK, 0.556, False),
        ("달빛 수선집 주제곡은 누가 불렀어?", DRAMA_CHUNK, 0.53, True),
        ("윤하람의 소속사는 어디야?", SINGER_CHUNK, 0.6, True),
        ("GOP API 인증은 어떻게 해?", "GOP RESTful API 연동 설계서", 0.631, True),
        ("아무 질문", "아무 상관 없는 내용", 0.70, True),  # 점수가 충분히 높으면 그대로
        ("윤하람 소속사", SINGER_CHUNK, 0.49, False),  # 기준 미만은 버린다
    ],
)
def test_should_keep_only_relevant_knowledge(query, chunk, score, expected) -> None:
    from shared.knowledge_filter import is_relevant

    assert is_relevant(query, chunk, score) is expected


def test_should_filter_result_list() -> None:
    from shared.knowledge_filter import relevant_results

    results = [
        {"content": GOP_JSON_CHUNK, "score": 0.56},
        {"content": SINGER_CHUNK, "score": 0.6},
    ]

    kept = relevant_results("윤하람의 소속사는 어디야?", results)

    assert [r["content"] for r in kept] == [SINGER_CHUNK]


@pytest.mark.asyncio
async def test_voice_turn_drops_unrelated_mid_score_chunk() -> None:
    from unittest.mock import AsyncMock, patch

    from services.orchestrator.app.orchestrator import Orchestrator

    with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
        orchestrator = Orchestrator(redis_client=AsyncMock())

    async def search(query):
        return [{"content": GOP_JSON_CHUNK, "score": 0.56, "metadata": {}}]

    orchestrator._search_knowledge = search

    assert await orchestrator._relevant_knowledge("오늘 날씨 알려줘") == []


@pytest.mark.asyncio
async def test_chat_drops_unrelated_mid_score_chunk() -> None:
    from unittest.mock import MagicMock

    from services.backend.app.services.chat_service import ChatService

    rag = MagicMock()

    async def retrieve(query, top_k=3):
        return [{"content": GOP_JSON_CHUNK, "score": 0.56, "source": "GOP.md"}]

    rag.retrieve = retrieve
    service = ChatService(llm_client=MagicMock(), rag_service=rag)

    assert await service._get_rag_context("오늘 날씨 알려줘") is None
