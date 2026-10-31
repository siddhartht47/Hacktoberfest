"""Loads the JSON data files and answers questions about them.

Everything here is plain Python with no web framework, so it is easy to test.
"""
from __future__ import annotations

import json
import re

from .config import DATA_DIR

# Words that carry no meaning when matching a free-text question to known problems.
STOP = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "do", "does", "for",
    "from", "get", "got", "have", "how", "i", "if", "in", "is", "it", "its", "me", "my",
    "no", "not", "of", "on", "or", "so", "that", "the", "then", "this", "to", "was",
    "what", "when", "why", "will", "with", "you", "your", "t", "s", "ollama",
}

# A model tag such as "gemma3:1b", "llama3.2:3b" or "hf.co/user/repo:Q4_K_M".
TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/]{0,80}(:[A-Za-z0-9._\-]{1,40})?$")

# Harmless things the helper model may mention in backticks.
BASE_ALLOWED = {"ctrl+c", "/bye", "sudo", "powershell"}


def _load(name: str) -> dict:
    with open(DATA_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


MODELS: list[dict] = _load("models.json")["models"]
_STEPS_FILE = _load("steps.json")
STEPS: list[dict] = _STEPS_FILE["steps"]
HARDWARE_HELP: dict = _STEPS_FILE["hardware_help"]
ERRORS: list[dict] = _load("errors.json")["errors"]


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower())) - STOP


for _e in ERRORS:
    _e["_re"] = [re.compile(p, re.I) for p in _e.get("patterns", [])]
    _e["_kw"] = _words(" ".join(_e.get("keywords", [])))
    _e["_tw"] = _words(_e["title"])


# --------------------------------------------------------------------------- models
def get_model(tag: str) -> dict:
    """Return a catalog model, or a 'custom' model if the tag looks valid."""
    tag = (tag or "").strip()
    for m in MODELS:
        if m["tag"].lower() == tag.lower():
            return m
    if TAG_RE.match(tag):
        return {
            "tag": tag, "name": tag, "family": "Custom", "params_b": None,
            "size_gb": None, "min_ram_gb": None, "rec_ram_gb": None,
            "goals": [], "blurb": "A model you chose yourself.", "custom": True,
        }
    raise ValueError("That model name does not look valid. Example: gemma3:1b")


# --------------------------------------------------------------------------- steps
def fmt(text: str | None, model: dict) -> str:
    """Fill {tag} and {size} placeholders."""
    if text is None:
        return ""
    size = model.get("size_gb")
    size_txt = f"about {size:g} GB" if size else "a few GB"
    return text.replace("{tag}", model["tag"]).replace("{size}", size_txt)


def get_raw_step(step_id: str) -> dict:
    for s in STEPS:
        if s["id"] == step_id:
            return s
    raise KeyError(step_id)


def _pick(table: dict, os_name: str):
    return table.get(os_name) or table.get("default")


def render_step(raw: dict, os_name: str, model: dict) -> dict:
    """Turn a raw step from steps.json into what the user sees."""
    cmds = _pick(raw["commands"], os_name) or []
    note = _pick(raw.get("notes", {}), os_name)
    return {
        "id": raw["id"],
        "title": fmt(raw["title"], model),
        "explain": fmt(raw["explain"], model),
        "commands": [fmt(c, model) for c in cmds],
        "note": fmt(note, model) if note else None,
        "expected": fmt(raw["expected"], model),
        "optional": bool(raw.get("optional", False)),
    }


def build_plan(os_name: str, model: dict) -> list[dict]:
    return [render_step(s, os_name, model) for s in STEPS]


# --------------------------------------------------------------------------- errors
def public_error(e: dict) -> dict:
    return {"id": e["id"], "title": e["title"], "cause": e["cause"], "fix": e["fix"]}


def _os_ok(e: dict, os_name: str) -> bool:
    return not e.get("os") or os_name in e["os"]


def match_errors(text: str, os_name: str, limit: int = 3) -> list[dict]:
    """Known problems whose patterns appear in pasted terminal output."""
    hits = [e for e in ERRORS if _os_ok(e, os_name) and any(r.search(text) for r in e["_re"])]
    return hits[:limit]


def search_errors(question: str, os_name: str, limit: int = 3) -> list[dict]:
    """Known problems that best match a free-text question."""
    tokens = _words(question)
    scored = []
    for e in ERRORS:
        if not _os_ok(e, os_name):
            continue
        score = 3 * len(tokens & e["_kw"]) + len(tokens & e["_tw"])
        if any(r.search(question) for r in e["_re"]):
            score += 10
        if score >= 3:
            scored.append((score, e))
    scored.sort(key=lambda pair: -pair[0])
    return [e for _, e in scored[:limit]]


# --------------------------------------------------------------------------- commands
def code_spans(text: str) -> list[str]:
    """Everything written between backticks."""
    return re.findall(r"`([^`]+)`", text or "")


def norm_cmd(cmd: str) -> str:
    return re.sub(r"\s+", " ", cmd.strip()).lower()


def allowed_commands(os_name: str, model: dict) -> set[str]:
    """Every command this app is willing to show. The helper AI may not go beyond it."""
    allowed = set(BASE_ALLOWED)
    for raw in STEPS:
        step = render_step(raw, os_name, model)
        for c in step["commands"]:
            allowed.add(norm_cmd(c))
        for text in (step["explain"], step["note"] or ""):
            allowed.update(norm_cmd(c) for c in code_spans(text))
    for e in ERRORS:
        for text in [e["cause"], *e["fix"]]:
            allowed.update(norm_cmd(c) for c in code_spans(text))
    return allowed
