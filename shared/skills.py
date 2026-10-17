"""
스킬 (설정 화면에서 켜고 끈다 — 백엔드 채팅·오케스트레이터 음성이 같이 쓴다)

- 내장 스킬: LLM 내장 도구(shared.tools). 끈 도구는 build_registry 가 뺀다.
- 프롬프트 스킬: 이름·설명·지시문. 켜면 지시문을 시스템 프롬프트 뒤에 붙인다.

    {"disabled_tools": ["web_fetch"],
     "prompts": [{"name": "존댓말", "description": "", "instructions": "...",
                  "enabled": true}]}
"""

import json
from typing import Any

# 백엔드 설정 API 가 쓰고 두 서비스가 턴마다 읽는다
SKILLS_KEY = "edgevoice:settings:skills"

# 내장 도구 이름 → 설정 화면에 보일 설명
BUILTIN_SKILLS = {
    "get_time": "지금 시각 알려 주기",
    "learn_note": "학습 노트 (기억해 둘 내용을 지식 베이스에 저장)",
    "get_weather": "날씨 (인터넷 도구가 켜져 있을 때)",
    "web_search": "인터넷 검색 (인터넷 도구가 켜져 있을 때)",
    "web_fetch": "웹 페이지 읽기 (인터넷 도구가 켜져 있을 때)",
}

SKILLS_HEADER = "[사용자가 켠 스킬 — 아래 지시를 따른다]"


def default_skills() -> dict:
    return {"disabled_tools": [], "prompts": []}


async def load_skills(redis: Any) -> dict:
    """설정 API 로 저장한 스킬(Redis) → 없으면 기본값(모두 켜짐, 프롬프트 스킬 없음)."""
    skills = default_skills()
    if redis is None:
        return skills
    try:
        raw = await redis.get(SKILLS_KEY)
        if raw:
            skills.update(json.loads(raw))
    except Exception:
        pass
    return skills


def with_skills(system_prompt: str, skills: dict) -> str:
    """켜진 프롬프트 스킬의 지시문을 시스템 프롬프트 뒤에 붙인다."""
    prompts = [p for p in skills.get("prompts", []) if p.get("enabled", True)]
    if not prompts:
        return system_prompt
    body = "\n\n".join(f"## {p['name']}\n{p['instructions']}" for p in prompts)
    return f"{system_prompt}\n\n{SKILLS_HEADER}\n{body}"
