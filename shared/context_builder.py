"""
대화 프롬프트 조립 (백엔드 채팅·오케스트레이터 음성이 같이 쓴다)

순서를 고정해 vLLM 접두사 캐시가 턴마다 맞도록 한다:
[고정 시스템 프롬프트 + 세션 요약] → [최근 턴] → [이번 질문 + RAG 근거]
- RAG 근거는 시스템 메시지에 섞지 않고 이번 사용자 메시지에 붙인다
  (시스템이 바뀌면 캐시가 깨진다).
- 프롬프트 + max_tokens 가 max_model_len 을 넘지 않게 오래된 턴부터 뺀다.
  최신 사용자 턴은 항상 넣는다.
"""

import os
from typing import Awaitable, Callable, Optional

DEFAULT_MAX_MODEL_LEN = int(os.getenv("LLM_MAX_MODEL_LEN", "16384"))
VOICE_MAX_TOKENS = 512
TEXT_MAX_TOKENS = 1024

# 채팅 템플릿 토큰(<|im_start|> 등)과 추정 오차를 위한 여유
SAFETY_TOKENS = 64
MESSAGE_OVERHEAD_TOKENS = 4

# 최근 턴이 입력 예산의 이 비율을 넘으면 오래된 턴을 요약으로 접는다
SUMMARY_TRIGGER_RATIO = 0.75
# 요약 후 원문으로 남길 최근 턴의 비율
SUMMARY_KEEP_RATIO = 0.4
# 추정치가 입력 예산의 이 비율을 넘을 때만 vLLM /tokenize 로 실제 토큰 수를 확인한다
VERIFY_RATIO = 0.5

SUMMARY_HEADER = "[이전 대화 요약]"

Message = dict
Tokenizer = Callable[[list], Awaitable[Optional[tuple]]]


def estimate_tokens(text: str) -> int:
    """토크나이저 없는 추정: UTF-8 3바이트(한글 한 글자)를 1토큰으로 본다."""
    return len(text.encode("utf-8")) // 3 + 1


def message_tokens(message: Message) -> int:
    return estimate_tokens(message.get("content") or "") + MESSAGE_OVERHEAD_TOKENS


def prompt_tokens(messages: list) -> int:
    return sum(message_tokens(m) for m in messages)


def input_budget(max_model_len: int, max_tokens: int) -> int:
    """프롬프트에 쓸 수 있는 토큰 수."""
    return max(0, max_model_len - max_tokens - SAFETY_TOKENS)


def build_system_content(system_prompt: str, summary: Optional[str] = None) -> str:
    """시스템 메시지. 시각 같은 매 턴 바뀌는 값은 넣지 않는다."""
    if summary:
        return (
            f"{system_prompt}\n\n{SUMMARY_HEADER}\n{summary}"
            if system_prompt
            else f"{SUMMARY_HEADER}\n{summary}"
        )
    return system_prompt


def _truncate_to_tokens(text: str, tokens: int) -> str:
    """앞에서부터 tokens 개 정도만 남긴다(추정 기준)."""
    if tokens <= 0:
        return ""
    data = text.encode("utf-8")
    return data[: tokens * 3].decode("utf-8", errors="ignore")


def build_messages(
    *,
    system_prompt: str,
    history: list,
    user_message: str,
    summary: Optional[str] = None,
    reference: Optional[str] = None,
    max_model_len: int = DEFAULT_MAX_MODEL_LEN,
    max_tokens: int = TEXT_MAX_TOKENS,
) -> list:
    """
    OpenAI 형식 messages 를 만든다.

    Args:
        system_prompt: 고정 시스템 프롬프트(빈 문자열이면 시스템 메시지를 보내지 않는다)
        history: 요약에 덮이지 않은 이전 메시지(시간순, role/content)
        user_message: 이번 사용자 질문
        summary: 세션 요약(있으면 시스템 메시지 끝 고정 위치)
        reference: RAG 근거 등 이번 질문에만 붙는 자료
            (제목까지 포함한 문자열, 질문 앞에 붙는다)
    """
    head = []
    system = build_system_content(system_prompt, summary)
    if system:
        head.append({"role": "system", "content": system})

    budget = input_budget(max_model_len, max_tokens) - prompt_tokens(head)

    # 최신 사용자 턴은 반드시 넣는다: 넘치면 참고 자료부터, 그다음 질문 앞부분만 남긴다
    question_tokens = estimate_tokens(user_message) + MESSAGE_OVERHEAD_TOKENS
    if question_tokens > budget:
        user_message = _truncate_to_tokens(
            user_message, budget - MESSAGE_OVERHEAD_TOKENS
        )
        reference = None
    content = user_message
    if reference:
        room = budget - question_tokens - 2
        reference = _truncate_to_tokens(reference, room)
        if reference:
            content = f"{reference}\n\n{user_message}"
    last = {"role": "user", "content": content}
    budget -= message_tokens(last)

    kept = []
    for message in reversed(history):
        cost = message_tokens(message)
        if cost > budget:
            break
        kept.append({"role": message["role"], "content": message["content"]})
        budget -= cost
    kept.reverse()

    return head + kept + [last]


async def fit_messages(
    build: Callable[[int], list],
    *,
    max_model_len: int,
    max_tokens: int,
    tokenize: Tokenizer,
) -> list:
    """
    build(max_model_len) 로 만든 프롬프트를 실제 토크나이저로 확인하고,
    넘치면 그만큼 줄여 다시 만든다.

    tokenize(messages) 는 (토큰 수, 서버 max_model_len) 또는 None(확인 불가)을 돌려준다.
    추정치가 예산에 한참 못 미치면 확인을 건너뛴다.
    """
    messages = build(max_model_len)
    if prompt_tokens(messages) <= VERIFY_RATIO * input_budget(
        max_model_len, max_tokens
    ):
        return messages

    limit = max_model_len
    for _ in range(3):
        result = await tokenize(messages)
        if result is None:
            return messages
        count, served_len = result
        overflow = count + max_tokens + SAFETY_TOKENS - min(limit, served_len)
        if overflow <= 0:
            return messages
        limit = min(limit, served_len) - overflow
        messages = build(limit)
    return messages


async def vllm_tokenize(base_url: str, model: str, messages: list) -> Optional[tuple]:
    """vLLM POST /tokenize(messages 형식) → (count, max_model_len). 실패하면 None."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{base_url}/tokenize", json={"model": model, "messages": messages}
            )
            response.raise_for_status()
            data = response.json()
            return int(data["count"]), int(data["max_model_len"])
    except Exception:
        return None


def split_for_summary(messages: list, max_model_len: int, max_tokens: int) -> int:
    """
    요약으로 접을 앞쪽 메시지 수. 접을 필요가 없으면 0.

    최근 턴이 입력 예산의 SUMMARY_TRIGGER_RATIO 를 넘으면,
    최근 턴이 SUMMARY_KEEP_RATIO 안에 들어올 때까지 앞에서부터 접는다.
    """
    budget = input_budget(max_model_len, max_tokens)
    total = prompt_tokens(messages)
    if total <= SUMMARY_TRIGGER_RATIO * budget:
        return 0

    keep_limit = SUMMARY_KEEP_RATIO * budget
    count = 0
    while count < len(messages) - 1 and total > keep_limit:
        total -= message_tokens(messages[count])
        count += 1
    return count
