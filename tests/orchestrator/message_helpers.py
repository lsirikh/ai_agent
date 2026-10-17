"""LLM 요청 메시지 비교 도우미."""


def without_reference(content: str) -> str:
    """이번 질문 앞에 붙는 근거 블록('[참고 자료] …\n\n질문')을 떼고 질문만 돌려준다.

    매 턴 지금 시각 근거가 붙으므로, 메시지 순서·중복을 보는 테스트는 질문만 비교한다.
    """
    if content.startswith("[참고 자료]"):
        return content.rsplit("\n\n", 1)[-1]
    return content


def roles_and_questions(messages: list) -> list:
    return [(m["role"], without_reference(m["content"])) for m in messages]
