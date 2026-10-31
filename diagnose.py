"""Checks the output a user pastes and explains what went wrong.

Order of trust:
  1. Regex rules from steps.json decide success.
  2. The error knowledge base (errors.json) supplies known causes and fixes.
  3. The helper model (Gemma) rephrases in plain words or guesses when nothing matches.
     Its commands are filtered: it may only mention commands this app already knows.
"""
from __future__ import annotations

import re

from . import knowledge as kb
from . import ollama_client
from .ollama_client import HelperUnavailable

SYSTEM_PROMPT = """You are a calm, friendly helper for complete beginners who are installing and running open-source AI models on their own computer with Ollama.
Rules:
- Use short, simple sentences. Explain any technical word in a few words.
- Only suggest commands that appear in the ALLOWED COMMANDS list. Never invent commands, flags or file paths.
- If the cause is unclear, say so and suggest the safest next step, such as running the command again or pasting the full output.
- Put every command inside backticks.
- Reply with JSON only, exactly in this shape: {"explanation": "<at most 3 sentences>", "next_steps": ["<step 1>", "<step 2>"]}
- At most 4 next steps."""

GENERIC_FIX = [
    "Make sure you ran exactly the command shown above, in a terminal.",
    "Paste the complete output, including any red error text.",
    "Use the \"Stuck?\" box below to describe what happened in your own words.",
]


def _result(status: str, headline: str, explanation: str = "", fix: list[str] | None = None,
            ai: dict | None = None, matched: list[dict] | None = None) -> dict:
    matched = matched or []
    return {
        "status": status,
        "headline": headline,
        "explanation": explanation,
        "fix": fix or [],
        "ai": ai,
        "ai_used": ai is not None,
        "matched_ids": [e["id"] for e in matched],
        "also_possible": [e["title"] for e in matched[1:]],
    }


# --------------------------------------------------------------------------- helper AI
def _clean_ai(data: dict, allowed: set[str]) -> dict | None:
    """Keep only well-formed text and drop anything that mentions an unknown command."""

    def ok(text: str) -> bool:
        return all(kb.norm_cmd(c) in allowed for c in kb.code_spans(text))

    explanation = data.get("explanation")
    explanation = explanation.strip()[:700] if isinstance(explanation, str) else ""
    if explanation and not ok(explanation):
        explanation = ""
    steps = []
    raw_steps = data.get("next_steps")
    if isinstance(raw_steps, list):
        for item in raw_steps:
            if isinstance(item, str) and item.strip() and ok(item):
                steps.append(item.strip()[:300])
    steps = steps[:4]
    if not explanation and not steps:
        return None
    return {"explanation": explanation, "next_steps": steps}


def _ask_helper(os_name: str, model: dict, step: dict | None, output: str | None,
                question: str | None, entries: list[dict]) -> dict | None:
    lines = [f"Operating system: {os_name}", f"Model the learner wants to run: {model['tag']}"]
    shown = set()
    if step:
        shown.update(step["commands"])
        lines += [
            f"Current step: {step['title']}",
            "Command shown to the learner: " + " ; ".join(step["commands"]),
            f"Expected result: {step['expected']}",
        ]
    if output:
        lines.append("Output the learner pasted:\n<<<\n" + output[-2500:] + "\n>>>")
    if question:
        lines.append("Learner's question: " + question[:1000])
    if entries:
        lines.append("Known causes and fixes from our knowledge base (trust these):")
        for e in entries:
            lines.append(f"- {e['title']}. {e['cause']} Fix: " + " | ".join(e["fix"]))
            for text in e["fix"]:
                shown.update(kb.code_spans(text))
    lines.append("ALLOWED COMMANDS: " + " ; ".join(sorted(shown)))

    try:
        data = ollama_client.chat_json(SYSTEM_PROMPT, "\n".join(lines))
    except HelperUnavailable:
        return None
    return _clean_ai(data, kb.allowed_commands(os_name, model))


# --------------------------------------------------------------------------- public API
def check_step(step_id: str, os_name: str, model: dict, output: str, use_ai: bool = True) -> dict:
    """Judge the output pasted for one step. Raises KeyError for an unknown step."""
    raw = kb.get_raw_step(step_id)
    step = kb.render_step(raw, os_name, model)
    text = (output or "").strip()
    if not text:
        return _result("empty", "Nothing to check yet",
                       "Paste the text your terminal printed after you ran the command, then press Check.")

    check = raw["check"]
    errors = kb.match_errors(text, os_name)

    if check["mode"] == "regex":
        tag = re.escape(model["tag"])
        success = any(re.search(p.replace("{tag}", tag), text, re.I) for p in check["success"])
    else:  # "nonempty": any reasonable output without a known error
        success = len(text) >= check.get("min_len", 20) and not errors

    if success:
        notes = [n["message"] for n in raw.get("success_notes", [])
                 if re.search(n["pattern"], text, re.I)]
        return _result("success", kb.fmt(raw["success_message"], model), " ".join(notes))

    if errors:
        main = errors[0]
        ai = _ask_helper(os_name, model, step, text, None, errors) if use_ai else None
        return _result("problem", main["title"], main["cause"], main["fix"], ai, errors)

    ai = _ask_helper(os_name, model, step, text, None, []) if use_ai else None
    return _result("unclear", "That does not look like the expected output",
                   f"Expected: {step['expected']}", GENERIC_FIX, ai)


def ask_help(question: str, os_name: str, model: dict, step_id: str | None, use_ai: bool = True) -> dict:
    """Answer a free-text 'I'm stuck' question."""
    entries = kb.match_errors(question, os_name)
    for e in kb.search_errors(question, os_name):
        if e not in entries:
            entries.append(e)
    entries = entries[:3]

    step = None
    if step_id:
        try:
            step = kb.render_step(kb.get_raw_step(step_id), os_name, model)
        except KeyError:
            step = None

    ai = _ask_helper(os_name, model, step, None, question, entries) if use_ai else None
    return {
        "matches": [kb.public_error(e) for e in entries],
        "ai": ai,
        "ai_used": ai is not None,
    }
