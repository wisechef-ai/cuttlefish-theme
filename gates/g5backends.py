"""Vision backends for G5. Each is ``fn(png_path, prompt) -> raw answer text``; exceptions mean a transport failure.

openrouter : OpenRouter chat completions with an image part; default anthropic/claude-sonnet-4.5, the model family Hermes' own
               auxiliary vision config names (key from env or ~/.hermes/.env).
codex  : OpenAI via ``codex exec -i`` run in an empty temp dir with user config and rules ignored, so no repo or design context loads.

DEVIATION (logged on t_0c601204): the Hermes ``vision_analyze`` path cannot be driven headless today. Its auxiliary vision
route resolves to an OpenRouter endpoint that answers 400 "claude-sonnet-5-5 is not a valid model ID" (default home) or
404 "no endpoints support image input" (builder home); Anthropic has no API key (OAuth only), the OpenAI API key has no credits
and the Gemini free tier allows 20 requests a day. The two backends here are different model families (Anthropic via OpenRouter,
OpenAI via codex) and independent of each other.

Only public renders, synthetic fixtures and openly licensed photos are ever sent. Hosted free tiers log prompts.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path

GATES_DIR = Path(__file__).resolve().parent
OPENROUTER_MODEL = os.environ.get("G5_OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5")
CODEX_MODEL = os.environ.get("G5_CODEX_MODEL", "")


def _env_key(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    env = Path.home() / ".hermes" / ".env"
    if env.is_file():
        for line in env.read_text().splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip("\"'")
    raise RuntimeError(f"{name} is not set (env or ~/.hermes/.env)")


def _post(url: str, headers: dict, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def openrouter_backend(png: Path, prompt: str, model: str = "") -> str:
    key = _env_key("OPENROUTER_API_KEY")
    b64 = base64.b64encode(Path(png).read_bytes()).decode()
    body = {"model": model or OPENROUTER_MODEL, "temperature": 0, "max_tokens": 1024, "messages": [{"role": "user", "content": [
        {"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]}
    d = _post("https://openrouter.ai/api/v1/chat/completions", {"Authorization": f"Bearer {key}"}, body)
    return d["choices"][0]["message"].get("content") or ""   # an empty/blocked reply is scored as invalid


def codex_backend(png: Path, prompt: str) -> str:
    with tempfile.TemporaryDirectory() as work:
        out = Path(work) / "answer.txt"
        cmd = ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "--ignore-rules", "--ignore-user-config", "-s", "read-only",
               "-i", str(png), "-o", str(out)] + (["-m", CODEX_MODEL] if CODEX_MODEL else []) + ["-"]
        p = subprocess.run(cmd, input=prompt, cwd=work, capture_output=True, text=True, timeout=240)
        if p.returncode != 0 or not out.exists():
            raise RuntimeError(f"codex exec failed rc={p.returncode}: {p.stderr.strip()[-300:]}")
        return out.read_text()


BACKENDS = {"openrouter": openrouter_backend, "codex": codex_backend}


def resolve(name: str):
    """'codex', 'openrouter' (default model) or 'openrouter:<vendor/model>' -> callable; None if unknown."""
    if name in BACKENDS:
        return BACKENDS[name]
    if name.startswith("openrouter:") and len(name) > len("openrouter:"):
        return lambda png, prompt: openrouter_backend(png, prompt, name.split(":", 1)[1])
    return None


def label(name: str) -> str:
    if name.startswith("openrouter:"):
        return f"openrouter {name.split(':', 1)[1]}"
    return {"openrouter": f"openrouter {OPENROUTER_MODEL}", "codex": f"openai via codex exec ({CODEX_MODEL or 'codex default model'})"}.get(name, name)
