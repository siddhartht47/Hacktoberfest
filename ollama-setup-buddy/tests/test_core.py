"""Tests for the framework-free core: recommender, step rendering and diagnosis."""
import pytest

from backend import diagnose, knowledge, ollama_client, recommender
from backend.ollama_client import HelperUnavailable


@pytest.fixture(autouse=True)
def helper_offline(monkeypatch):
    """By default pretend the helper model is unavailable so tests never need Ollama."""
    def boom(*args, **kwargs):
        raise HelperUnavailable("offline in tests")
    monkeypatch.setattr(ollama_client, "chat_json", boom)


def model(tag="gemma3:1b"):
    return knowledge.get_model(tag)


def check(step, os_name, output, tag="gemma3:1b", use_ai=True):
    return diagnose.check_step(step, os_name, model(tag), output, use_ai)


# ----------------------------------------------------------------- recommender
def test_8gb_no_gpu_recommends_gemma_4b():
    r = recommender.recommend(8, 0, 50, "chat")
    assert r["recommended"] == "gemma3:4b"


def test_16gb_no_gpu_prefers_8b_class_not_12b():
    r = recommender.recommend(16, 0, 100, "chat")
    assert r["recommended"] == "llama3.1:8b"
    gemma12 = next(m for m in r["models"] if m["tag"] == "gemma3:12b")
    assert gemma12["fit"] == "slow"


def test_gpu_makes_big_model_fast():
    r = recommender.recommend(16, 12, 100, "chat")
    gemma12 = next(m for m in r["models"] if m["tag"] == "gemma3:12b")
    assert gemma12["fit"] == "gpu"


def test_tiny_ram_recommends_nothing():
    r = recommender.recommend(2, 0, 50, "chat")
    assert r["recommended"] is None
    assert all(m["rank"] >= 3 for m in r["models"])


def test_low_disk_flags_models():
    r = recommender.recommend(32, 0, 3, "chat")
    big = next(m for m in r["models"] if m["tag"] == "llama3.1:8b")
    assert big["fit"] == "disk"


def test_light_goal_picks_smallest_first():
    r = recommender.recommend(8, 0, 50, "light")
    assert r["recommended"] == "gemma3:1b"


def test_coding_goal_picks_coder():
    r = recommender.recommend(16, 0, 50, "coding")
    assert r["recommended"] == "qwen2.5-coder:7b"


def test_exactly_one_recommended_flag():
    r = recommender.recommend(8, 0, 50, "chat")
    assert sum(1 for m in r["models"] if m["recommended"]) == 1


# ----------------------------------------------------------------- models & plan
def test_custom_model_accepted_and_bad_rejected():
    assert knowledge.get_model("mistral:7b")["family"] == "Mistral"
    assert knowledge.get_model("some-new-model:3b")["custom"] is True
    for bad in ["", "rm -rf /", "a b", "x;y", "$(whoami)"]:
        with pytest.raises(ValueError):
            knowledge.get_model(bad)


@pytest.mark.parametrize("os_name", ["windows", "macos", "linux"])
def test_plan_fills_in_model_tag(os_name):
    plan = knowledge.build_plan(os_name, model("mistral:7b"))
    pull = next(s for s in plan if s["id"] == "pull")
    assert pull["commands"] == ["ollama pull mistral:7b"]
    assert all(s["commands"] for s in plan)
    assert not any("{tag}" in s["title"] + s["explain"] + s["expected"] for s in plan)


def test_install_commands_differ_per_os():
    cmds = {o: knowledge.build_plan(o, model())[0]["commands"][0] for o in ("windows", "macos", "linux")}
    assert "install.ps1" in cmds["windows"]
    assert "brew" in cmds["macos"]
    assert "install.sh" in cmds["linux"]


def test_data_files_are_consistent():
    ids = [e["id"] for e in knowledge.ERRORS]
    assert len(ids) == len(set(ids))
    for m in knowledge.MODELS:
        assert m["size_gb"] > 0 and m["min_ram_gb"] <= m["rec_ram_gb"]
    for s in knowledge.STEPS:
        assert s["check"]["mode"] in ("regex", "nonempty")


# ----------------------------------------------------------------- check_step: success
def test_version_success():
    assert check("version", "linux", "ollama version is 0.12.3")["status"] == "success"


def test_version_with_server_warning_still_succeeds_with_note():
    out = "Warning: could not connect to a running Ollama instance\nWarning: client version is 0.12.3"
    r = check("version", "linux", out)
    assert r["status"] == "success"
    assert "server is not running" in r["explanation"]


def test_server_success():
    assert check("server", "windows", "Ollama is running")["status"] == "success"


def test_pull_success():
    out = "pulling manifest\npulling 8648f39daa8f: 100%\nverifying sha256 digest\nwriting manifest\nsuccess"
    assert check("pull", "macos", out)["status"] == "success"


def test_list_success_uses_chosen_tag():
    out = "NAME ID SIZE MODIFIED\nmistral:7b abc 4.1 GB 2 minutes ago"
    assert check("list", "linux", out, tag="mistral:7b")["status"] == "success"
    assert check("list", "linux", out, tag="gemma3:1b")["status"] != "success"


def test_run_success_needs_real_answer():
    ok = "Open-source software is software whose source code is freely available to everyone."
    assert check("run", "linux", ok)["status"] == "success"
    assert check("run", "linux", "hi")["status"] == "unclear"


def test_python_versions():
    assert check("python", "linux", "Python 3.12.4")["status"] == "success"
    assert check("python", "linux", "Python 3.10.0")["status"] == "success"
    old = check("python", "linux", "Python 3.9.18")
    assert old["status"] == "problem" and "python_old" in old["matched_ids"]


# ----------------------------------------------------------------- check_step: problems
@pytest.mark.parametrize("step,os_name,output,expected_id", [
    ("version", "windows", "ollama : The term 'ollama' is not recognized as the name of a cmdlet", "ollama_not_found"),
    ("version", "linux", "bash: ollama: command not found", "ollama_not_found"),
    ("server", "linux", "curl: (7) Failed to connect to localhost port 11434 after 0 ms: Couldn't connect to server", "server_not_running"),
    ("server", "windows", "Invoke-RestMethod : Unable to connect to the remote server", "server_not_running"),
    ("pull", "linux", "Error: pull model manifest: file does not exist", "model_not_found"),
    ("pull", "linux", "Error: pull model manifest: Get \"https://registry.ollama.ai/v2\": net/http: TLS handshake timeout", "network_failure"),
    ("pull", "windows", "Error: write C:\\Users\\a\\.ollama\\models\\blobs: There is not enough space on the disk.", "disk_full"),
    ("run", "linux", "Error: model requires more system memory (5.6 GiB) than is available (3.1 GiB)", "not_enough_memory"),
    ("install", "windows", "File C:\\x.ps1 cannot be loaded because running scripts is disabled on this system.", "powershell_policy"),
    ("install", "linux", "bash: line 1: curl: command not found", "curl_missing"),
    ("install", "linux", "mkdir: cannot create directory: Permission denied", "permission_denied"),
    ("install", "macos", "\"Ollama\" cannot be opened because the developer cannot be verified.", "mac_blocked"),
    ("server", "linux", "System has not been booted with systemd as init system", "systemd_missing"),
    ("run", "linux", "Error: llama runner process has terminated: exit status 2", "model_crash"),
    ("git", "windows", "git : The term 'git' is not recognized as the name of a cmdlet", "git_missing"),
])
def test_known_errors_are_recognised(step, os_name, output, expected_id):
    r = check(step, os_name, output)
    assert r["status"] == "problem", r
    assert r["matched_ids"][0] == expected_id
    assert r["fix"], "every known error needs a fix"


def test_os_specific_errors_do_not_leak_across_systems():
    r = check("install", "linux", "File x.ps1 cannot be loaded because running scripts is disabled")
    assert "powershell_policy" not in r["matched_ids"]


def test_unknown_output_is_unclear_with_generic_fix():
    r = check("pull", "linux", "something completely unexpected happened here")
    assert r["status"] == "unclear" and r["fix"]


def test_empty_output():
    assert check("pull", "linux", "   ")["status"] == "empty"


def test_unknown_step_raises():
    with pytest.raises(KeyError):
        check("nope", "linux", "x")


# ----------------------------------------------------------------- helper AI
def test_ai_failure_falls_back_to_rules():
    r = check("version", "linux", "bash: ollama: command not found", use_ai=True)
    assert r["status"] == "problem" and r["ai"] is None and r["ai_used"] is False


def test_ai_answer_is_attached(monkeypatch):
    monkeypatch.setattr(ollama_client, "chat_json", lambda s, u: {
        "explanation": "The terminal does not know where Ollama is.",
        "next_steps": ["Close the terminal and open a new one.", "Run `ollama --version` again."],
    })
    r = check("version", "linux", "bash: ollama: command not found")
    assert r["ai_used"] and len(r["ai"]["next_steps"]) == 2


def test_ai_invented_commands_are_dropped(monkeypatch):
    monkeypatch.setattr(ollama_client, "chat_json", lambda s, u: {
        "explanation": "Try this.",
        "next_steps": ["Run `sudo rm -rf /` now.", "Run `ollama --version` again."],
    })
    r = check("version", "linux", "bash: ollama: command not found")
    assert r["ai"]["next_steps"] == ["Run `ollama --version` again."]


def test_ai_explanation_with_unknown_command_is_dropped(monkeypatch):
    monkeypatch.setattr(ollama_client, "chat_json", lambda s, u: {
        "explanation": "Run `format c:` to fix it.", "next_steps": [],
    })
    r = check("version", "linux", "bash: ollama: command not found")
    assert r["ai"] is None


def test_ai_garbage_shapes_are_ignored(monkeypatch):
    monkeypatch.setattr(ollama_client, "chat_json", lambda s, u: {"explanation": 5, "next_steps": "no"})
    r = check("version", "linux", "bash: ollama: command not found")
    assert r["ai"] is None


def test_ai_can_be_switched_off(monkeypatch):
    called = []
    monkeypatch.setattr(ollama_client, "chat_json", lambda s, u: called.append(1) or {"explanation": "x"})
    check("version", "linux", "bash: ollama: command not found", use_ai=False)
    assert not called


def test_ai_used_for_unmatched_output(monkeypatch):
    monkeypatch.setattr(ollama_client, "chat_json", lambda s, u: {
        "explanation": "I am not sure what this means.", "next_steps": ["Run `ollama --version` again."]})
    r = check("pull", "linux", "weird output nobody has seen")
    assert r["status"] == "unclear" and r["ai_used"]


# ----------------------------------------------------------------- ask_help
def test_ask_slow_question_finds_slow_entry():
    r = diagnose.ask_help("my model is very slow and the laptop fan is loud", "linux", model(), None)
    assert r["matches"] and r["matches"][0]["id"] == "too_slow"


def test_ask_with_pasted_error_text():
    r = diagnose.ask_help("it says command not found: ollama", "linux", model(), "version")
    assert r["matches"][0]["id"] == "ollama_not_found"


def test_ask_nothing_matches_returns_empty_list():
    r = diagnose.ask_help("zzz qqq xxx", "linux", model(), None)
    assert r["matches"] == [] and r["ai"] is None


# ----------------------------------------------------------------- ollama client parsing
def test_json_parsing_recovers_from_wrapped_text():
    assert ollama_client._parse_json('Sure! {"a": 1} hope that helps')["a"] == 1
    with pytest.raises(HelperUnavailable):
        ollama_client._parse_json("no json here")
