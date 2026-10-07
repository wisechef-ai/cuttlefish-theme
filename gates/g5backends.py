"""Vision backends for G5. Each is ``fn(png_path, prompt) -> raw answer text``; exceptions mean a transport failure.

gemini : Google generativelanguage REST (key from env or ~/.hermes/.env).
codex  : OpenAI via ``codex exec -i`` run in an empty temp dir with user config and rules ignored, so no repo or design context loads.

DEVIATION (logged on t_0c601204): the Hermes ``vision_analyze`` path cannot be driven headless today. Its auxiliary vision
route resolves to an OpenRouter endpoint that answers 400 "claude-sonnet-5-5 is not a valid model ID" (default home) or
404 "no endpoints support image input" (builder home); the Anthropic route is OAuth-only (no API key) and the OpenAI API key has
no credits. The two backends here are different model families (Google, OpenAI) and independent of each other.

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
GEMINI_MODEL = os.environ.get("G5_GEMINI_MODEL", "gemini-2.5-flash")
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


def gemini_backend(png: Path, prompt: str) -> str:
    key = _env_key("GEMINI_API_KEY")
    b64 = base64.b64encode(Path(png).read_bytes()).decode()
    body = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/png", "data": b64}}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 2048}}
    d = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent", {"x-goog-api-key": key}, body)
    cands = d.get("candidates") or []
    parts = (cands[0].get("content", {}).get("parts") if cands else None) or []
    return "".join(p.get("text", "") for p in parts)   # a blocked/empty reply returns "" and is scored as invalid


def codex_backend(png: Path, prompt: str) -> str:
    with tempfile.TemporaryDirectory() as work:
        out = Path(work) / "answer.txt"
        cmd = ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "--ignore-rules", "--ignore-user-config", "-s", "read-only",
               "-i", str(png), "-o", str(out)] + (["-m", CODEX_MODEL] if CODEX_MODEL else []) + ["-"]
        p = subprocess.run(cmd, input=prompt, cwd=work, capture_output=True, text=True, timeout=240)
        if p.returncode != 0 or not out.exists():
            raise RuntimeError(f"codex exec failed rc={p.returncode}: {p.stderr.strip()[-300:]}")
        return out.read_text()


BACKENDS = {"gemini": gemini_backend, "codex": codex_backend}
MODEL_LABELS = {"gemini": f"google {GEMINI_MODEL}", "codex": f"openai via codex exec ({CODEX_MODEL or 'codex default model'})"}
