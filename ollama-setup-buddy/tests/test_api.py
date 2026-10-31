"""HTTP-level tests. Needs fastapi and httpx (pip install -r requirements-dev.txt)."""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from backend import ollama_client  # noqa: E402
from backend.main import app  # noqa: E402
from backend.ollama_client import HelperUnavailable  # noqa: E402


@pytest.fixture(autouse=True)
def helper_offline(monkeypatch):
    def boom(*args, **kwargs):
        raise HelperUnavailable("offline in tests")
    monkeypatch.setattr(ollama_client, "chat_json", boom)
    monkeypatch.setattr(ollama_client, "status",
                        lambda: {"online": False, "model": "gemma3:1b", "model_ready": False})


client = TestClient(app)


def test_frontend_is_served():
    r = client.get("/")
    assert r.status_code == 200 and "Ollama Setup Buddy" in r.text


def test_config_and_health():
    assert client.get("/api/health").json()["online"] is False
    cfg = client.get("/api/config").json()
    assert set(cfg["os"]) == {"windows", "macos", "linux"} and "windows" in cfg["hardware_help"]


def test_recommend():
    r = client.post("/api/recommend", json={"ram_gb": 8, "vram_gb": 0, "disk_gb": 50, "goal": "chat"})
    assert r.status_code == 200 and r.json()["recommended"] == "gemma3:4b"


def test_recommend_validation():
    assert client.post("/api/recommend", json={"ram_gb": -1}).status_code == 422
    assert client.post("/api/recommend", json={"ram_gb": 8, "goal": "nonsense"}).status_code == 422


def test_plan():
    r = client.post("/api/plan", json={"os": "windows", "model": "llama3.2:3b"})
    assert r.status_code == 200
    steps = r.json()["steps"]
    assert next(s for s in steps if s["id"] == "pull")["commands"] == ["ollama pull llama3.2:3b"]


def test_plan_rejects_bad_input():
    assert client.post("/api/plan", json={"os": "amiga", "model": "gemma3:1b"}).status_code == 422
    assert client.post("/api/plan", json={"os": "linux", "model": "rm -rf /"}).status_code == 400


def test_check_success_and_problem():
    ok = client.post("/api/check", json={"os": "linux", "model": "gemma3:1b", "step_id": "version",
                                         "output": "ollama version is 0.12.3"}).json()
    assert ok["status"] == "success"
    bad = client.post("/api/check", json={"os": "linux", "model": "gemma3:1b", "step_id": "version",
                                          "output": "bash: ollama: command not found"}).json()
    assert bad["status"] == "problem" and bad["matched_ids"] == ["ollama_not_found"]


def test_check_unknown_step_is_404():
    r = client.post("/api/check", json={"os": "linux", "model": "gemma3:1b", "step_id": "zzz", "output": "x"})
    assert r.status_code == 404


def test_ask():
    r = client.post("/api/ask", json={"os": "linux", "model": "gemma3:1b",
                                      "question": "the download is stuck at 99%"})
    assert r.status_code == 200 and r.json()["matches"]
