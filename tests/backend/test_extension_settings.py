"""
설정 화면의 MCP·스킬 API (사용자 요청 2026-10-18)

- MCP 서버 목록(연결 상태·도구)·추가·수정·삭제·켜기/끄기. 저장하면 채팅 도구에 바로 반영
- 스킬: 내장 도구 켜기/끄기 + 프롬프트 스킬(켜면 채팅 시스템 프롬프트에 붙는다)
"""

import json
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.backend.app.services import conversation

pytest.importorskip("mcp")

SERVER = os.path.join(
    os.path.dirname(__file__), os.pardir, "shared", "mcp_test_server.py"
)


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value):
        self.values[key] = value


def _server(**overrides):
    values = {
        "name": "ironwall",
        "command": sys.executable,
        "args": [SERVER],
        "allowed_tools": ["status", "restart"],
        "trusted": True,
        "timeout": 30,
    }
    values.update(overrides)
    return values


@pytest.fixture
def client(monkeypatch, tmp_path):
    from services.backend.app.routes import chat, extensions, settings

    path = tmp_path / "servers.json"
    path.write_text(json.dumps({"servers": [_server()]}), encoding="utf-8")
    monkeypatch.setenv("MCP_CONFIG_PATH", str(path))
    redis = FakeRedis()
    monkeypatch.setattr(conversation, "_get_redis", lambda: redis)
    monkeypatch.setattr(chat, "_mcp", None)
    app = FastAPI()
    app.include_router(extensions.router)
    app.include_router(settings.router)
    # 한 이벤트 루프에서 MCP 연결이 요청 사이에 이어지게 한다
    with TestClient(app) as test_client:
        yield test_client
        test_client.portal.call(chat.stop_mcp)


def _mcp_tool_names(client):
    from services.backend.app.routes import chat

    return [n for n in client.portal.call(chat.get_tools).names() if "__" in n]


class TestMcpServers:
    def test_lists_servers_from_config_file_with_connection_and_tools(self, client):
        servers = client.get("/api/settings/mcp").json()["servers"]

        assert [s["name"] for s in servers] == ["ironwall"]
        assert servers[0]["enabled"] is True
        assert servers[0]["status"] == "connected"
        assert {"status", "restart"} <= set(servers[0]["tools"])

    def test_turning_off_disconnects_and_removes_tools_from_chat(self, client):
        off = client.put("/api/settings/mcp/ironwall", json=_server(enabled=False))

        assert off.json()["servers"][0]["status"] == "disabled"
        assert _mcp_tool_names(client) == []

        on = client.put("/api/settings/mcp/ironwall", json=_server(enabled=True))

        assert on.json()["servers"][0]["status"] == "connected"
        assert _mcp_tool_names(client) == ["ironwall__restart", "ironwall__status"]

    def test_add_edit_and_delete_server(self, client):
        added = client.post(
            "/api/settings/mcp", json=_server(name="extra", allowed_tools=["status"])
        )
        assert [s["name"] for s in added.json()["servers"]] == ["ironwall", "extra"]
        assert "extra__status" in _mcp_tool_names(client)

        client.put(
            "/api/settings/mcp/extra",
            json=_server(name="extra", allowed_tools=["restart"]),
        )
        names = _mcp_tool_names(client)
        assert "extra__restart" in names and "extra__status" not in names

        deleted = client.delete("/api/settings/mcp/extra")
        assert [s["name"] for s in deleted.json()["servers"]] == ["ironwall"]
        assert not any(n.startswith("extra__") for n in _mcp_tool_names(client))

    def test_saved_list_persists_in_redis(self, client):
        from shared.mcp_client import MCP_SETTINGS_KEY

        client.put("/api/settings/mcp/ironwall", json=_server(enabled=False))

        saved = json.loads(conversation._get_redis().values[MCP_SETTINGS_KEY])
        assert saved[0]["name"] == "ironwall" and saved[0]["enabled"] is False

    def test_rejects_duplicates_unknown_names_and_missing_target(self, client):
        assert client.post("/api/settings/mcp", json=_server()).status_code == 409
        assert (
            client.put("/api/settings/mcp/none", json=_server(name="none")).status_code
            == 404
        )
        assert client.delete("/api/settings/mcp/none").status_code == 404
        no_target = {"name": "x", "allowed_tools": []}
        assert client.post("/api/settings/mcp", json=no_target).status_code == 422


class TestSkills:
    def test_builtin_skills_are_listed_and_enabled_by_default(self, client):
        body = client.get("/api/settings/skills").json()

        builtin = {s["name"]: s for s in body["builtin"]}
        expected = {"get_time", "learn_note", "web_search", "web_fetch", "get_weather"}
        assert expected <= set(builtin)
        assert all(s["enabled"] for s in builtin.values())
        assert builtin["get_time"]["active"] is True
        assert body["prompts"] == []

    def test_turning_off_builtin_skill_removes_it_from_tools(self, client):
        body = client.put(
            "/api/settings/skills", json={"disabled_tools": ["get_time"], "prompts": []}
        ).json()

        builtin = {s["name"]: s for s in body["builtin"]}
        assert builtin["get_time"]["enabled"] is False
        assert "get_time" not in client.get("/api/settings/tools").json()["tools"]

    def test_prompt_skills_are_saved(self, client):
        skill = {
            "name": "존댓말",
            "description": "항상 존댓말",
            "instructions": "항상 존댓말로 답한다.",
            "enabled": True,
        }

        client.put(
            "/api/settings/skills", json={"disabled_tools": [], "prompts": [skill]}
        )

        assert client.get("/api/settings/skills").json()["prompts"] == [skill]

    def test_rejects_duplicate_prompt_skill_names(self, client):
        skill = {"name": "a", "instructions": "x"}

        response = client.put(
            "/api/settings/skills", json={"prompts": [skill, skill]}
        )

        assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_system_prompt_gets_enabled_prompt_skills(monkeypatch):
    from unittest.mock import MagicMock

    from services.backend.app.services.chat_service import ChatService
    from shared.skills import SKILLS_KEY

    redis = FakeRedis()
    redis.values[SKILLS_KEY] = json.dumps(
        {"prompts": [{"name": "존댓말", "instructions": "항상 존댓말로 답한다."}]}
    )
    monkeypatch.setattr(conversation, "_get_redis", lambda: redis)
    prompts = []

    async def stream(text, system_prompt=None, **kwargs):
        prompts.append(system_prompt)
        yield "네"

    llm = MagicMock()
    llm.generate_stream = stream

    async for _ in ChatService(llm_client=llm).process_message(
        session_id="s", message="안녕", use_rag=False
    ):
        pass

    assert "항상 존댓말로 답한다." in prompts[0]


def test_settings_list_shows_new_desktop_tools_from_project_config(monkeypatch):
    # 실제 config/mcp/servers.json 을 연결 없이 목록으로만 보여 준다
    from services.backend.app.routes import chat, extensions
    from shared.mcp_client import MCPManager

    root = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
    monkeypatch.setenv(
        "MCP_CONFIG_PATH", os.path.join(root, "config", "mcp", "servers.json")
    )
    monkeypatch.setattr(conversation, "_get_redis", lambda: FakeRedis())

    async def offline():
        return MCPManager([])

    monkeypatch.setattr(chat, "sync_mcp", offline)
    app = FastAPI()
    app.include_router(extensions.router)

    servers = {
        s["name"]: s for s in TestClient(app).get("/api/settings/mcp").json()["servers"]
    }

    desktop = servers["desktop"]
    new_tools = ("draw_picture", "mouse_click", "mouse_drag", "type_text", "press_keys")
    for tool in new_tools:
        assert tool in desktop["allowed_tools"] and tool in desktop["no_confirm"]
    assert desktop["enabled"] is True and desktop["status"] == "disconnected"
