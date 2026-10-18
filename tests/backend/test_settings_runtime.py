"""
설정 화면이 실제 실행 값을 보여 주는지 (저장값과 실행값 구분, 정직한 재시작)
"""

import subprocess

import pytest
from fastapi.testclient import TestClient

from services.backend.app.main import app
from services.backend.app.routes import settings as settings_route


def _hub(tmp_path, *hf_paths):
    for hf_path in hf_paths:
        snapshot = (
            tmp_path / ("models--" + hf_path.replace("/", "--")) / "snapshots" / "abc"
        )
        snapshot.mkdir(parents=True)
        (snapshot / "config.json").write_text("{}")
    return tmp_path


def test_llm_option_id_maps_served_model():
    assert (
        settings_route.llm_option_id("Qwen/Qwen2.5-7B-Instruct-AWQ")
        == "qwen2.5-7b-instruct-awq"
    )
    assert (
        settings_route.llm_option_id("qwen2.5-7b-instruct-awq")
        == "qwen2.5-7b-instruct-awq"
    )
    assert settings_route.llm_option_id("unknown/Model") == "unknown/Model"


def test_voice_falls_back_to_engine_default():
    assert settings_route.voice_for_engine("melo", "ko-KR-SunHiNeural") == "KR"
    assert settings_route.voice_for_engine("kokoro", "af_bella") == "af_bella"
    assert settings_route.voice_for_engine("edge_tts", "KR") == "ko-KR-SunHiNeural"


def test_llm_options_only_downloaded(tmp_path, monkeypatch):
    # 폴더만 있고 snapshot 이 없는 모델은 받지 않은 것으로 본다
    (tmp_path / "models--deepseek-ai--DeepSeek-R1-Distill-Llama-8B").mkdir()
    monkeypatch.setattr(
        settings_route,
        "LLM_HUB_DIR",
        str(_hub(tmp_path, "Qwen/Qwen2.5-7B-Instruct-AWQ")),
    )

    assert [m["id"] for m in settings_route.get_llm_options()] == [
        "qwen2.5-7b-instruct-awq"
    ]


def test_options_current_is_runtime_and_marks_pending(monkeypatch):
    runtime = {
        "llm_model": "qwen2.5-7b-instruct-awq",
        "stt_model": "small",
        "tts_engine": "melo",
        "tts_voice": "KR",
        "wake_word_threshold": 0.3,
    }

    async def fake_runtime():
        return runtime

    saved = settings_route.AllSettings(
        stt=settings_route.STTSettings(model_size="medium")
    )
    monkeypatch.setattr(settings_route, "read_runtime_settings", fake_runtime)
    monkeypatch.setattr(settings_route, "get_settings", lambda: saved)
    data = TestClient(app).get("/api/settings/options").json()

    assert {k: data["current"][k] for k in runtime} == runtime
    assert data["saved"]["stt_model"] == "medium"
    assert "stt_model" in data["pending_restart"]
    assert data["tts_voices"]["melo"] == ["KR"]
    # 응답한 서비스의 실행 값만 따로 (다시 시작 뒤 '반영됨' 확인용)
    assert data["runtime"] == runtime


def test_options_runtime_skips_services_not_answering(monkeypatch):
    async def fake_runtime():
        return {"llm_model": "qwen2.5-7b-instruct-awq"}

    monkeypatch.setattr(settings_route, "read_runtime_settings", fake_runtime)
    data = TestClient(app).get("/api/settings/options").json()

    assert "stt_model" not in data["runtime"]
    assert "stt_model" in data["current"]


def test_apply_rejects_not_downloaded_llm(tmp_path, monkeypatch):
    monkeypatch.setattr(
        settings_route,
        "LLM_HUB_DIR",
        str(_hub(tmp_path, "Qwen/Qwen2.5-7B-Instruct-AWQ")),
    )
    before = settings_route._current_settings.llm.model

    data = (
        TestClient(app)
        .post(
            "/api/settings/apply",
            json={"changes": {"llm": {"model": "deepseek-r1-distill-llama-8b"}}},
        )
        .json()
    )

    assert data["applied"]["llm"] is False
    assert "llm" in data["errors"]
    assert settings_route._current_settings.llm.model == before


def test_apply_engine_change_moves_voice(monkeypatch):
    monkeypatch.setattr(settings_route, "sync_settings_to_env", lambda *a, **k: True)
    monkeypatch.setattr(settings_route, "save_settings_to_db", lambda *a, **k: True)
    TestClient(app).post(
        "/api/settings/apply",
        json={"changes": {"tts": {"engine": "melo", "voice": "ko-KR-SunHiNeural"}}},
    )

    assert settings_route._current_settings.tts.voice == "KR"


def test_llm_restart_fails_honestly(monkeypatch):
    monkeypatch.delenv("COMPOSE_PROJECT_DIR", raising=False)
    response = TestClient(app).post("/api/services/llm/restart")

    assert response.status_code == 503
    assert response.json()["status"] == "failed"
    assert "docker compose up -d llm" in response.json()["message"]


@pytest.mark.parametrize("service", ["stt", "tts"])
def test_model_service_restart_fails_honestly(monkeypatch, service):
    monkeypatch.delenv("COMPOSE_PROJECT_DIR", raising=False)
    response = TestClient(app).post(f"/api/services/{service}/restart")

    assert response.status_code == 503
    assert response.json()["service"] == service
    assert f"docker compose up -d {service}" in response.json()["message"]


def test_service_restart_recreates_with_compose(monkeypatch, tmp_path):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs["cwd"]))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setenv("COMPOSE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(subprocess, "run", fake_run)
    response = TestClient(app).post("/api/services/stt/restart")

    assert response.status_code == 200
    assert response.json()["status"] == "restarting"
    assert calls == [(["docker", "compose", "up", "-d", "stt"], str(tmp_path))]


def test_unknown_service_restart_is_rejected():
    response = TestClient(app).post("/api/services/postgres/restart")

    assert response.status_code == 422


def test_startup_env_sync_skips_llm_model():
    assert "model" not in settings_route.get_current_settings_as_dict()["llm"]


def test_startup_env_sync_skips_stt_model():
    # compose 가 읽는 STT_MODEL 은 사용자가 STT 모델을 저장할 때만 쓴다
    assert "model" not in settings_route.get_current_settings_as_dict()["stt"]
