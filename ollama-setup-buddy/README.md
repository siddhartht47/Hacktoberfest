# Ollama Setup Buddy

A small web app that walks a complete beginner through installing and running **open-source AI models** (Gemma, Llama, Mistral, Qwen, Phi, DeepSeek and more) on their own computer with [Ollama](https://ollama.com).

> We use an open-source model to help anyone get started with open-source models.

## The problem

Open-source AI is free and private, but the first hour is where most beginners give up: the terminal can't find `ollama`, port 11434 is in use, the model is too big for their RAM, the download times out. Guides are static and can't react to what actually happens on your machine.

## What it does

1. **Your computer:** pick your OS and enter RAM, GPU memory, free disk and your goal.
2. **Model:** a rule-based recommender rates every model for your machine (fast / runs on CPU / tight / too large / not enough disk). You can also type any model tag from the Ollama library.
3. **Guided install:** one step at a time (install Ollama, check version, check server, pull the model, list, run it), with a copy button for each command.
4. **Check your output:** paste what the terminal printed. The app confirms success, or recognises the problem and explains the fix.
5. **Stuck?** Describe the problem in your own words and get matching known fixes.

## How the checking works (and why it is trustworthy)

| Layer | What it does |
|---|---|
| 1. Rules (`steps.json`) | Regex checks decide whether a step succeeded. No AI involved. |
| 2. Knowledge base (`errors.json`) | 20 known problems with causes and fixes, matched by pattern and by keywords. |
| 3. Helper AI (Gemma via Ollama) | Rewrites the cause and fix in plain words, or makes a best guess for unknown output. |

The helper AI is optional. Without it, the app still works with layers 1 and 2. Its answers are filtered: **any command in backticks that the app does not already know is dropped**, so the AI cannot invent commands. The app never runs commands for you.

## Quick start

Requires Python 3.10+.

```bash
git clone <your-repo-url>
cd ollama-setup-buddy

python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# macOS / Linux:       source .venv/bin/activate

python -m pip install -r requirements.txt
python run.py
```

Open <http://localhost:8000>.

### Turn on the helper AI (optional)

```bash
ollama pull gemma3:1b
```

Keep Ollama running. The header of the app shows "Helper AI: gemma3:1b is ready" when it is connected.

| Environment variable | Default | Meaning |
|---|---|---|
| `HELPER_MODEL` | `gemma3:1b` | Model used by the helper. Try `gemma3:4b` for better explanations. |
| `HELPER_OLLAMA_URL` | `http://localhost:11434` | Where the helper's Ollama server runs. |
| `HELPER_TIMEOUT` | `90` | Seconds before falling back to rules only. |

## Project layout

```
backend/
  main.py          FastAPI routes + serves the frontend
  knowledge.py     loads the JSON data, matches errors, renders steps
  recommender.py   rule-based model recommender
  diagnose.py      checks pasted output, calls the helper AI, filters its commands
  ollama_client.py tiny client for the helper model
  config.py        settings
  data/
    models.json    model catalog (tags, sizes, RAM needs)
    steps.json     install steps per OS + success checks
    errors.json    known problems, patterns, fixes
frontend/          plain HTML, CSS and JavaScript (no build step)
tests/             pytest suite
```

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Is the helper model reachable? |
| GET | `/api/config` | OS list, hardware tips, helper status |
| POST | `/api/recommend` | Rate every model for the user's hardware |
| POST | `/api/plan` | Steps for an OS and model |
| POST | `/api/check` | Check pasted output for one step |
| POST | `/api/ask` | Free-text "I'm stuck" question |

Interactive docs: <http://localhost:8000/docs>

## Extend it

- **Add a model:** add an entry to `backend/data/models.json`. Verify the tag and size at <https://ollama.com/library>.
- **Add a known error:** add an entry to `backend/data/errors.json` with `patterns` (regex), `keywords`, `cause` and `fix`. Put commands in backticks.
- **Add or change a step:** edit `backend/data/steps.json`. Use `{tag}` for the chosen model.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

## Limitations

- Model sizes in `models.json` are approximate. Check them against the Ollama library before a demo.
- Install commands come from the official Ollama pages and the Hacktoberfest prerequisites guide. If a command changes upstream, update `steps.json`.
- The recommender uses simple rules of thumb for RAM and VRAM, not benchmarks.
- Not medical, legal or security advice; it only helps with installing software.

## Credits and disclosures

- [Ollama](https://ollama.com) (MIT) runs the models.
- [Gemma](https://ai.google.dev/gemma) by Google DeepMind powers the optional helper. Llama, Mistral, Qwen, Phi and DeepSeek models are listed as installable choices under their own licenses; check each model's license before use.
- [FastAPI](https://fastapi.tiangolo.com), [Uvicorn](https://www.uvicorn.org), [Requests](https://requests.readthedocs.io).
- Setup steps follow the *Hacktoberfest 2026 Day 2 Instructor Prerequisites & System Readiness Guide*.
- **AI-assisted development:** this project was generated with the help of Claude (Anthropic) and then reviewed and tested by the team. Add your own notes here about what you verified or changed.

## License

MIT. See `LICENSE`.
