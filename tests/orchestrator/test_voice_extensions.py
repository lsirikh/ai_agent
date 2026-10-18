"""
음성 경로의 MCP·스킬 설정 (사용자 요청 2026-10-18)

- 설정 화면에서 켜고 끈 MCP 서버를 재시작 없이 턴마다 맞춘다
- 켠 프롬프트 스킬은 시스템 프롬프트에 붙는다
"""

import json

import pytest

from shared.mcp_client import MCP_SETTINGS_KEY
from shared.skills import SKILLS_KEY
from tests.orchestrator.test_voice_tools import make, text_chunk, voice_turn


def _redis_values(orchestrator, values):
    async def get(key):
        return values.get(key)

    orchestrator.redis.get.side_effect = get


class FakeMCP:
    def __init__(self):
        self.applied = []

    async def apply(self, configs):
        self.applied.append(configs)

    async def tools(self):
        return []


@pytest.mark.asyncio
async def test_tools_follow_saved_mcp_settings_each_turn():
    orchestrator, *_ = make([])
    orchestrator.mcp = FakeMCP()
    servers = [
        {"name": "browser", "url": "http://b/mcp", "enabled": True},
        {"name": "desktop", "url": "http://d/mcp", "enabled": False},
    ]
    _redis_values(orchestrator, {MCP_SETTINGS_KEY: json.dumps(servers)})

    await orchestrator._build_tools()

    applied = orchestrator.mcp.applied[-1]
    assert [(c.name, c.enabled) for c in applied] == [
        ("browser", True),
        ("desktop", False),
    ]


@pytest.mark.asyncio
async def test_disabled_builtin_skill_is_not_offered_by_voice():
    orchestrator, *_ = make([])
    _redis_values(
        orchestrator, {SKILLS_KEY: json.dumps({"disabled_tools": ["get_time"]})}
    )

    registry = await orchestrator._build_tools()

    assert "get_time" not in registry.names()


@pytest.mark.asyncio
async def test_enabled_prompt_skill_is_added_to_voice_system_prompt():
    orchestrator, _, requests, _ = make([[text_chunk("네, 알겠습니다.")]])
    skills = {
        "prompts": [
            {"name": "짧게", "instructions": "한 문장으로만 답한다.", "enabled": True}
        ]
    }
    _redis_values(orchestrator, {SKILLS_KEY: json.dumps(skills)})

    await voice_turn(orchestrator, "오늘 뭐 할까?")

    system = requests[0]["messages"][0]
    assert system["role"] == "system"
    assert system["content"].startswith("음성 비서")
    assert "한 문장으로만 답한다." in system["content"]
