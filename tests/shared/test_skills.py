"""
스킬 — 설정 화면에서 내장 도구를 켜고 끄고, 프롬프트형 스킬을 시스템 프롬프트에 붙인다
(사용자 요청 2026-10-18).
"""

import json

import pytest

from shared.skills import SKILLS_KEY, load_skills, with_skills
from shared.tools import Tool, build_registry, load_tool_settings


class FakeRedis:
    def __init__(self, values=None):
        self.values = dict(values or {})

    async def get(self, key):
        return self.values.get(key)


def test_disabled_builtin_tools_are_left_out():
    settings = {"internet_enabled": False, "disabled_tools": ["learn_note"]}

    assert build_registry(settings).names() == ["get_time"]


def test_disabled_tools_do_not_remove_mcp_tools():
    mcp_tool = Tool(name="browser__x", description="", parameters={}, run=None)
    settings = {"disabled_tools": ["get_time", "learn_note"]}

    assert build_registry(settings, [mcp_tool]).names() == ["browser__x"]


@pytest.mark.asyncio
async def test_tool_settings_carry_disabled_tools_from_skills():
    redis = FakeRedis({SKILLS_KEY: json.dumps({"disabled_tools": ["get_time"]})})

    settings = await load_tool_settings(redis)

    assert settings["disabled_tools"] == ["get_time"]
    assert "get_time" not in build_registry(settings).names()


@pytest.mark.asyncio
async def test_load_skills_defaults_when_nothing_saved():
    assert await load_skills(None) == {"disabled_tools": [], "prompts": []}
    assert await load_skills(FakeRedis()) == {"disabled_tools": [], "prompts": []}


def test_enabled_prompt_skills_are_appended_to_system_prompt():
    skills = {
        "prompts": [
            {"name": "존댓말", "instructions": "존댓말로 답한다.", "enabled": True},
            {"name": "꺼짐", "instructions": "이 문장은 빠진다.", "enabled": False},
        ]
    }

    prompt = with_skills("기본 프롬프트", skills)

    assert prompt.startswith("기본 프롬프트")
    assert "## 존댓말\n존댓말로 답한다." in prompt
    assert "이 문장은 빠진다." not in prompt


def test_no_enabled_prompt_skills_keeps_prompt_unchanged():
    assert with_skills("기본", {"prompts": []}) == "기본"
