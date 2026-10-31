"""FastAPI application: JSON API under /api, static frontend at /."""
from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import diagnose, knowledge, ollama_client, recommender
from .config import FRONTEND_DIR

OSName = Literal["windows", "macos", "linux"]
Goal = Literal["chat", "coding", "reasoning", "light"]

app = FastAPI(title="Ollama Setup Buddy", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- request bodies
class RecommendRequest(BaseModel):
    ram_gb: float = Field(..., gt=0, le=4096)
    vram_gb: float = Field(0, ge=0, le=1024)
    disk_gb: float | None = Field(None, ge=0, le=100000)
    goal: Goal = "chat"


class PlanRequest(BaseModel):
    os: OSName
    model: str = Field(..., min_length=1, max_length=100)


class CheckRequest(BaseModel):
    os: OSName
    model: str = Field(..., min_length=1, max_length=100)
    step_id: str = Field(..., min_length=1, max_length=40)
    output: str = Field("", max_length=20000)
    use_ai: bool = True


class AskRequest(BaseModel):
    os: OSName
    model: str = Field(..., min_length=1, max_length=100)
    question: str = Field(..., min_length=3, max_length=2000)
    step_id: str | None = Field(None, max_length=40)
    use_ai: bool = True


def _model(tag: str) -> dict:
    try:
        return knowledge.get_model(tag)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# --------------------------------------------------------------------------- routes
@app.get("/api/health")
def health():
    """Is the helper model (Gemma through Ollama) reachable?"""
    return ollama_client.status()


@app.get("/api/config")
def config():
    return {
        "os": ["windows", "macos", "linux"],
        "goals": list(recommender.GOALS),
        "hardware_help": knowledge.HARDWARE_HELP,
        "helper": ollama_client.status(),
    }


@app.post("/api/recommend")
def recommend(req: RecommendRequest):
    return recommender.recommend(req.ram_gb, req.vram_gb, req.disk_gb, req.goal)


@app.post("/api/plan")
def plan(req: PlanRequest):
    model = _model(req.model)
    return {
        "model": {"tag": model["tag"], "name": model["name"], "size_gb": model["size_gb"]},
        "steps": knowledge.build_plan(req.os, model),
    }


@app.post("/api/check")
def check(req: CheckRequest):
    model = _model(req.model)
    try:
        return diagnose.check_step(req.step_id, req.os, model, req.output, req.use_ai)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown step")


@app.post("/api/ask")
def ask(req: AskRequest):
    model = _model(req.model)
    return diagnose.ask_help(req.question, req.os, model, req.step_id, req.use_ai)


# Must be mounted last so it does not shadow the /api routes.
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
