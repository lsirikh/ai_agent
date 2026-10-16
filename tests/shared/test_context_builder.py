"""
공통 ContextBuilder 시나리오

- 예산: 긴 메시지가 많아도 프롬프트 + max_tokens ≤ max_model_len, 최신 턴은 항상 포함
- 접두사 안정: 연속 두 턴의 [시스템 + 요약] 접두사가 바이트 단위로 같음
- 요약: 임계값을 넘으면 앞쪽 턴을 접을 개수를 돌려준다
"""

import pytest

from shared.context_builder import (
    SUMMARY_HEADER,
    build_messages,
    fit_messages,
    input_budget,
    prompt_tokens,
    split_for_summary,
)

SYSTEM = "당신은 EdgeVoice 비서입니다."


def _long_history(count: int, chars: int = 400) -> list:
    return [
        {
            "role": "user" if i % 2 == 0 else "assistant",
            "content": f"{i}번째 " + "가" * chars,
        }
        for i in range(count)
    ]


class TestBudget:
    def test_should_fit_model_len_when_history_has_200_long_messages(self):
        messages = build_messages(
            system_prompt=SYSTEM,
            history=_long_history(200),
            user_message="마지막 질문",
            max_model_len=4096,
            max_tokens=512,
        )

        assert prompt_tokens(messages) + 512 <= 4096
        assert messages[0]["role"] == "system"
        assert messages[-1] == {"role": "user", "content": "마지막 질문"}
        # 최근 턴부터 남는다
        assert messages[-2]["content"].startswith("199번째")

    def test_should_keep_latest_turn_when_question_alone_exceeds_budget(self):
        messages = build_messages(
            system_prompt=SYSTEM,
            history=_long_history(4),
            user_message="나" * 10000,
            reference="참고" * 1000,
            max_model_len=2048,
            max_tokens=512,
        )

        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"].startswith("나")
        assert prompt_tokens(messages) + 512 <= 2048

    def test_should_put_reference_in_user_message_not_system(self):
        messages = build_messages(
            system_prompt=SYSTEM,
            history=[],
            user_message="질문",
            reference="[참고 자료]\n문서 내용",
        )

        assert messages[0]["content"] == SYSTEM
        assert messages[-1]["content"] == "[참고 자료]\n문서 내용\n\n질문"

    def test_should_omit_system_message_when_prompt_is_empty(self):
        messages = build_messages(system_prompt="", history=[], user_message="질문")

        assert messages == [{"role": "user", "content": "질문"}]

    @pytest.mark.asyncio
    async def test_should_rebuild_smaller_when_tokenizer_reports_overflow(self):
        """추정이 실제보다 작아도 vLLM /tokenize 결과로 다시 줄여 400 을 막는다."""
        history = _long_history(200)

        def build(limit: int) -> list:
            return build_messages(
                system_prompt=SYSTEM,
                history=history,
                user_message="질문",
                max_model_len=limit,
                max_tokens=512,
            )

        async def tokenize(messages: list):
            # 실제 토크나이저는 추정의 1.5배를 센다고 가정
            return int(prompt_tokens(messages) * 1.5), 4096

        messages = await fit_messages(
            build, max_model_len=4096, max_tokens=512, tokenize=tokenize
        )

        assert int(prompt_tokens(messages) * 1.5) + 512 <= 4096
        assert messages[-1]["content"] == "질문"

    @pytest.mark.asyncio
    async def test_should_skip_tokenizer_when_prompt_is_small(self):
        calls = []

        async def tokenize(messages: list):
            calls.append(messages)
            return 0, 4096

        def build(limit: int) -> list:
            return build_messages(
                system_prompt=SYSTEM,
                history=[],
                user_message="안녕",
                max_model_len=limit,
            )

        await fit_messages(build, max_model_len=4096, max_tokens=512, tokenize=tokenize)

        assert calls == []


class TestPrefixStability:
    def test_should_keep_system_and_summary_prefix_identical_across_turns(self):
        history = _long_history(6, chars=20)
        summary = "사용자 이름은 민수다."

        first = build_messages(
            system_prompt=SYSTEM,
            history=history,
            user_message="첫 질문",
            summary=summary,
            reference="[참고 자료]\nA",
        )
        history += [
            {"role": "user", "content": "첫 질문"},
            {"role": "assistant", "content": "답"},
        ]
        second = build_messages(
            system_prompt=SYSTEM,
            history=history,
            user_message="둘째 질문",
            summary=summary,
            reference="[참고 자료]\nB",
        )

        assert first[0]["content"].encode("utf-8") == second[0]["content"].encode(
            "utf-8"
        )
        assert first[0]["content"] == f"{SYSTEM}\n\n{SUMMARY_HEADER}\n{summary}"
        # 이전 턴들도 같은 순서로 이어져 접두사가 그대로 재사용된다
        assert second[1 : len(first) - 1] == first[1:-1]


class TestSummarySplit:
    def test_should_not_fold_when_under_threshold(self):
        assert split_for_summary(_long_history(4, chars=20), 16384, 1024) == 0

    def test_should_fold_oldest_until_recent_turns_fit_keep_ratio(self):
        history = _long_history(200)
        budget = input_budget(16384, 1024)
        assert prompt_tokens(history) > 0.75 * budget

        fold = split_for_summary(history, 16384, 1024)

        assert 0 < fold < len(history)
        assert prompt_tokens(history[fold:]) <= 0.4 * budget
