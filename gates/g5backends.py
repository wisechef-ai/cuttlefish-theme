"""Vision backends for G5. Each is ``fn(png_path, prompt) -> raw answer text``; exceptions mean a transport failure.

qwen   : qwen3.8-27b on hercules (OpenAI-compatible, local, private-safe; HERCULES_API_KEY; model via G5_QWEN_MODEL; thinking off).
glm    : zai glm-4.6v-flash (OpenAI-compatible, free tier; GLM_API_KEY; model via G5_GLM_MODEL). Paced (G5_GLM_MIN_INTERVAL, default 3 s)
         because 3 concurrent workers draw 429s; 429/5xx are retried with exponential backoff + jitter, bounded, then a TransportError.
codex  : OpenAI via ``codex exec -i`` run in an empty temp dir with user config and rules ignored, so no repo or design context loads (optional).
gemini:<model> : Google generativelanguage REST (GEMINI_API_KEY; free tier is 20 requests/day per model: smoke only).
openrouter : OpenRouter chat completions with an image part (optional; default anthropic/claude-sonnet-4.5).

The default pair is ``qwen,glm``: two independent model families that are free/local, so a full gate run costs nothing and never
leaves the quota.

DEVIATION (D-R2-4, logged on t_0c601204): the Hermes ``vision_analyze`` path cannot be driven headless today. Its auxiliary vision
route resolves to an OpenRouter endpoint that answers 400 "claude-sonnet-5-5 is not a valid model ID" (default home) or
404 "no endpoints support image input" (builder home); Anthropic has no API key (OAuth only), the OpenAI API key has no credits
and the Gemini free tier allows 20 requests a day. So the gate calls the two vision models directly instead of through vision_analyze.
That is separate from the instrument and is tracked as its own defect.

Only public renders, synthetic fixtures and openly licensed photos are ever sent. Hosted free tiers (zai) log prompts.
"""
from __future__ import annotations

import base64
import dataclasses
import json
import os
import random
import subprocess
import tempfile
import threading
import time
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


_pace_lock, _pace_last = threading.Lock(), [0.0]
GEMINI_MIN_INTERVAL = float(os.environ.get("G5_GEMINI_MIN_INTERVAL", "4.0"))   # free tier: pace calls instead of hammering


def gemini_backend(png: Path, prompt: str, model: str = "gemini-3-flash-preview") -> str:
    with _pace_lock:
        time.sleep(max(0.0, _pace_last[0] + GEMINI_MIN_INTERVAL - time.monotonic()))
        _pace_last[0] = time.monotonic()
    b64 = base64.b64encode(Path(png).read_bytes()).decode()
    body = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/png", "data": b64}}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 2048, "responseMimeType": "application/json"}}
    d = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", {"x-goog-api-key": _env_key("GEMINI_API_KEY")}, body)
    cands = d.get("candidates") or []
    parts = (cands[0].get("content", {}).get("parts") if cands else None) or []
    return "".join(p.get("text", "") for p in parts)   # a blocked/empty reply is scored as invalid


DEFAULT_BACKENDS = "qwen,glm"
BACKOFF_BASE = 2.0           # seconds; doubles per retry, plus up to BACKOFF_BASE of jitter
RETRYABLE = {408, 425, 429, 500, 502, 503, 504}


class TransportError(RuntimeError):
    """A model call failed for good (after the bounded retries, or a non-retryable status). Recorded, never invented around."""


class Pacer:
    """Min interval between the starts of calls on one backend (thread-safe; injectable clock for tests)."""

    def __init__(self, clock=time.monotonic, sleep=time.sleep):
        self._lock, self._last, self._clock, self._sleep = threading.Lock(), None, clock, sleep

    def wait(self, interval: float) -> None:
        with self._lock:
            if self._last is not None:
                self._sleep(max(0.0, self._last + interval - self._clock()))
            self._last = self._clock()


@dataclasses.dataclass(frozen=True)
class OpenAICompat:
    url: str
    key_name: str
    model: str
    min_interval: float = 0.0
    max_retries: int = 5
    extra_body: dict = dataclasses.field(default_factory=dict)
    pacer: Pacer = dataclasses.field(default_factory=Pacer, compare=False)


def _status(e: Exception):
    return getattr(e, "status", None) or getattr(e, "code", None)


def openai_compat_call(cfg: OpenAICompat, png: Path, prompt: str, post=None, sleep=time.sleep, key: str | None = None, rand=random.random) -> str:
    """One OpenAI-compatible chat call with an image part: paced, 429/5xx retried with exponential backoff + jitter, bounded."""
    post = post or _post
    key = key or _env_key(cfg.key_name)
    b64 = base64.b64encode(Path(png).read_bytes()).decode()
    body = {"model": cfg.model, "temperature": 0, "max_tokens": 1024, **cfg.extra_body, "messages": [{"role": "user", "content": [
        {"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]}
    last = ""
    for attempt in range(cfg.max_retries + 1):
        if cfg.min_interval:
            cfg.pacer.wait(cfg.min_interval)
        try:
            d = post(cfg.url, {"Authorization": f"Bearer {key}"}, body)
            return (d["choices"][0]["message"].get("content") or "") if d.get("choices") else ""   # empty/blocked reply is scored as invalid
        except Exception as e:  # noqa: BLE001
            st = _status(e)
            last = f"{type(e).__name__}: {e}"[:300]
            if st is not None and st not in RETRYABLE:
                raise TransportError(f"{cfg.model}: non-retryable {last}") from e
            if attempt < cfg.max_retries:
                sleep(BACKOFF_BASE * (2 ** attempt) + rand() * BACKOFF_BASE)
    raise TransportError(f"{cfg.model}: gave up after {cfg.max_retries} retries: {last}")


def model_id(name: str) -> str:
    if name == "qwen":
        return os.environ.get("G5_QWEN_MODEL") or "qwen3.8-27b-heretic"
    if name == "glm":
        return os.environ.get("G5_GLM_MODEL") or "glm-4.6v-flash"
    if name == "codex":
        return CODEX_MODEL or "codex-default"
    if name.startswith(("openrouter:", "gemini:")):
        return name.split(":", 1)[1]
    return {"openrouter": OPENROUTER_MODEL}.get(name, name)


_GLM_PACER, _QWEN_PACER = Pacer(), Pacer()


def qwen_backend(png: Path, prompt: str) -> str:
    cfg = OpenAICompat(url=os.environ.get("G5_QWEN_URL", "http://100.106.27.136:8000/v1/chat/completions"), key_name="HERCULES_API_KEY",
                       model=model_id("qwen"), extra_body={"chat_template_kwargs": {"enable_thinking": False}}, pacer=_QWEN_PACER)
    return openai_compat_call(cfg, png, prompt)


def glm_backend(png: Path, prompt: str) -> str:
    cfg = OpenAICompat(url="https://api.z.ai/api/paas/v4/chat/completions", key_name="GLM_API_KEY", model=model_id("glm"),
                       min_interval=float(os.environ.get("G5_GLM_MIN_INTERVAL", "3.0")), pacer=_GLM_PACER)
    return openai_compat_call(cfg, png, prompt)


qwen_backend.retries_internal = glm_backend.retries_internal = True


def codex_backend(png: Path, prompt: str) -> str:
    with tempfile.TemporaryDirectory() as work:
        out = Path(work) / "answer.txt"
        cmd = ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "--ignore-rules", "--ignore-user-config", "-s", "read-only",
               "-i", str(png), "-o", str(out)] + (["-m", CODEX_MODEL] if CODEX_MODEL else []) + ["-"]
        p = subprocess.run(cmd, input=prompt, cwd=work, capture_output=True, text=True, timeout=240)
        if p.returncode != 0 or not out.exists():
            raise RuntimeError(f"codex exec failed rc={p.returncode}: {p.stderr.strip()[-300:]}")
        return out.read_text()


BACKENDS = {"qwen": qwen_backend, "glm": glm_backend, "openrouter": openrouter_backend, "codex": codex_backend}


def resolve(name: str):
    """'qwen', 'glm', 'codex', 'gemini:<model>', 'openrouter' (default model) or 'openrouter:<vendor/model>' -> callable; None if unknown."""
    if name in BACKENDS:
        return BACKENDS[name]
    if name.startswith("openrouter:") and len(name) > len("openrouter:"):
        return lambda png, prompt: openrouter_backend(png, prompt, name.split(":", 1)[1])
    if name.startswith("gemini:") and len(name) > len("gemini:"):
        return lambda png, prompt: gemini_backend(png, prompt, name.split(":", 1)[1])
    return None


def label(name: str) -> str:
    if name.startswith(("openrouter:", "gemini:")):
        return name.replace(":", " ", 1)
    return {"qwen": f"qwen via hercules ({model_id('qwen')})", "glm": f"zai {model_id('glm')}", "openrouter": f"openrouter {OPENROUTER_MODEL}", "codex": f"openai via codex exec ({CODEX_MODEL or 'codex default model'})"}.get(name, name)
