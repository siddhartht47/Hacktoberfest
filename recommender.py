"""Rule-based model recommender. No AI needed: simple, predictable and explainable."""
from __future__ import annotations

from .knowledge import MODELS

GOALS = ("chat", "coding", "reasoning", "light")


def assess(model: dict, ram_gb: float, vram_gb: float, disk_gb: float | None) -> dict:
    """How well does one model fit this computer? Lower rank is better."""
    size = model["size_gb"]
    if disk_gb is not None and disk_gb < size + 2:
        return {"fit": "disk", "rank": 4, "label": f"Needs about {size + 2:.0f} GB of free disk"}
    if vram_gb >= size * 1.25:
        return {"fit": "gpu", "rank": 0, "label": "Fast: fits in your GPU"}
    if ram_gb >= model["rec_ram_gb"]:
        if model["params_b"] > 8:
            return {"fit": "slow", "rank": 2, "label": "Works, but slowly without a GPU"}
        return {"fit": "cpu", "rank": 1, "label": "Runs on your CPU"}
    if ram_gb >= model["min_ram_gb"]:
        return {"fit": "tight", "rank": 2, "label": "Tight: expect it to be slow"}
    return {"fit": "too_big", "rank": 3, "label": "Too large for your RAM"}


def _size_class(params_b: float) -> int:
    if params_b < 2.5:
        return 1
    if params_b < 5:
        return 2
    return 3


def recommend(ram_gb: float, vram_gb: float, disk_gb: float | None, goal: str) -> dict:
    """Return every catalog model with a fit rating, best choices first."""
    rows = []
    for index, m in enumerate(MODELS):
        a = assess(m, ram_gb, vram_gb, disk_gb)
        tier = 0 if a["rank"] <= 1 else a["rank"]
        mismatch = 0 if goal in m["goals"] else 1
        quality = m["size_gb"] if goal == "light" else -_size_class(m["params_b"])
        rows.append(((tier, mismatch, quality, index), {**m, **a}))
    rows.sort(key=lambda pair: pair[0])
    models = [row for _, row in rows]

    recommended = None
    for m in models:
        if m["rank"] <= 1 and goal in m["goals"]:
            recommended = m["tag"]
            break
    if recommended is None:
        for m in models:
            if m["rank"] <= 2:
                recommended = m["tag"]
                break
    for m in models:
        m["recommended"] = m["tag"] == recommended
    return {"models": models, "recommended": recommended}
