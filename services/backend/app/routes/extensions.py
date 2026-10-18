"""
Backend API - MCP 서버·스킬 설정 (사용자 요청 2026-10-18)

- MCP: 목록(연결 상태·도구)·추가·수정·삭제·켜기/끄기. 저장하면 채팅은 바로 다시 연결하고
  오케스트레이터(음성)는 다음 턴에 같은 설정으로 맞춘다 (MCPManager.apply).
- 스킬: 내장 도구 켜기/끄기 + 프롬프트 스킬(켜면 시스템 프롬프트에 붙는다).
"""
import json
from dataclasses import asdict
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from shared.mcp_client import MCP_SETTINGS_KEY, MCPServerConfig, load_mcp_servers
from shared.skills import BUILTIN_SKILLS, SKILLS_KEY, load_skills
from shared.tools import build_registry, load_tool_settings

from ..services import conversation
from . import chat

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ===== MCP 서버 =====

class MCPServerSettings(BaseModel):
    """MCP 서버 하나 (shared.mcp_client.MCPServerConfig 와 같은 모양)."""
    name: str = Field(min_length=1, max_length=64)
    url: Optional[str] = None
    command: Optional[str] = None
    args: List[str] = []
    env: Optional[Dict[str, str]] = None
    allowed_tools: List[str] = []
    trusted: bool = False
    always_confirm: List[str] = []
    no_confirm: List[str] = []
    timeout: float = Field(default=30.0, gt=0)
    enabled: bool = True

    @model_validator(mode="after")
    def _needs_target(self) -> "MCPServerSettings":
        if not (self.url or self.command):
            raise ValueError("url 또는 command 가 필요합니다")
        return self


async def _mcp_response() -> dict:
    """서버마다 설정 + 연결 상태(connected·disconnected·disabled)·오류·서버 도구."""
    configs = await load_mcp_servers(conversation._get_redis())
    manager = await chat.sync_mcp()
    await manager.tools()  # 연결된 서버의 도구 목록을 새로 받는다
    servers = {server.config.name: server for server in manager.servers}
    result = []
    for config in configs:
        server = servers.get(config.name) if config.enabled else None
        if not config.enabled:
            status = "disabled"
        elif server is not None and server.client is not None:
            status = "connected"
        else:
            status = "disconnected"
        result.append({
            **asdict(config),
            "status": status,
            "error": str(server.error) if server is not None and server.error else "",
            "tools": [t.name for t in server.tools] if status == "connected" else [],
        })
    return {"servers": result}


async def _save_mcp(configs: list) -> dict:
    await conversation._get_redis().set(
        MCP_SETTINGS_KEY, json.dumps([asdict(c) for c in configs], ensure_ascii=False)
    )
    return await _mcp_response()


def _check_unique(name: str, configs: list) -> None:
    if any(c.name == name for c in configs):
        raise HTTPException(status_code=409, detail=f"이미 있는 이름입니다: {name}")


async def _mcp_configs_with(name: str) -> list:
    configs = await load_mcp_servers(conversation._get_redis())
    if all(c.name != name for c in configs):
        raise HTTPException(status_code=404, detail=f"없는 MCP 서버입니다: {name}")
    return configs


@router.get("/mcp")
async def get_mcp_servers():
    """MCP 서버 목록과 연결 상태 (설정 화면에서 저장한 것, 없으면 MCP_CONFIG_PATH)."""
    return await _mcp_response()


@router.post("/mcp")
async def add_mcp_server(server: MCPServerSettings):
    configs = await load_mcp_servers(conversation._get_redis())
    _check_unique(server.name, configs)
    return await _save_mcp(configs + [MCPServerConfig(**server.model_dump())])


@router.put("/mcp/{name}")
async def update_mcp_server(name: str, server: MCPServerSettings):
    """서버 설정 바꾸기 (켜기/끄기는 enabled). 이름을 바꿀 수도 있다."""
    configs = await _mcp_configs_with(name)
    if server.name != name:
        _check_unique(server.name, configs)
    updated = MCPServerConfig(**server.model_dump())
    return await _save_mcp([updated if c.name == name else c for c in configs])


@router.delete("/mcp/{name}")
async def delete_mcp_server(name: str):
    configs = await _mcp_configs_with(name)
    return await _save_mcp([c for c in configs if c.name != name])


# ===== 스킬 =====

class PromptSkill(BaseModel):
    """프롬프트 스킬: 켜면 지시문이 시스템 프롬프트 뒤에 붙는다."""
    name: str = Field(min_length=1, max_length=64)
    description: str = ""
    instructions: str = Field(min_length=1)
    enabled: bool = True


class SkillSettings(BaseModel):
    # 끈 내장 스킬(도구) 이름
    disabled_tools: List[str] = []
    prompts: List[PromptSkill] = []

    @field_validator("prompts")
    @classmethod
    def _unique_names(cls, prompts: List[PromptSkill]) -> List[PromptSkill]:
        names = [p.name for p in prompts]
        if len(names) != len(set(names)):
            raise ValueError("스킬 이름이 겹칩니다")
        return prompts


async def _skills_response() -> dict:
    redis = conversation._get_redis()
    skills = await load_skills(redis)
    # 지금 LLM 에 실제로 노출되는 도구 (인터넷 도구가 꺼져 있으면 켜 둔 스킬도 빠진다)
    active = build_registry(await load_tool_settings(redis)).names()
    return {
        "builtin": [
            {
                "name": name,
                "description": description,
                "enabled": name not in skills["disabled_tools"],
                "active": name in active,
            }
            for name, description in BUILTIN_SKILLS.items()
        ],
        "disabled_tools": skills["disabled_tools"],
        "prompts": skills["prompts"],
    }


@router.get("/skills")
async def get_skills():
    return await _skills_response()


@router.put("/skills")
async def update_skills(skills: SkillSettings):
    """스킬 설정 전체를 저장한다 — 다음 턴부터 음성·채팅에 반영된다."""
    await conversation._get_redis().set(
        SKILLS_KEY, json.dumps(skills.model_dump(), ensure_ascii=False)
    )
    return await _skills_response()
