"""Throwaway spike plugin: register every hook in VALID_HOOKS, append payloads as JSONL."""
import json, os, time, threading

_seq = 0
_lock = threading.Lock()
_ID_KEYS = ("session_id", "session_key", "task_id", "turn_id", "parent_session_id",
            "stored_session_id", "child_session_id", "platform", "surface", "old_session_id",
            "new_session_id", "tool_name", "tool_call_id", "choice", "decided_by", "aux_task",
            "reason", "completed", "failed", "interrupted", "turn_exit_reason", "model",
            "status_code", "error_type", "api_call_count", "pattern_key", "provider")

def _summ(v):
    if isinstance(v, (str, int, float, bool)) or v is None:
        s = v if not isinstance(v, str) else v[:120]
        return {"t": type(v).__name__, "v": s}
    if isinstance(v, (list, tuple)):
        return {"t": type(v).__name__, "len": len(v)}
    if isinstance(v, dict):
        return {"t": "dict", "keys": sorted(map(str, v))[:20]}
    return {"t": type(v).__name__}

def _make(name):
    def cb(**kw):
        global _seq
        with _lock:
            _seq += 1
            n = _seq
        row = {"ts": round(time.time(), 3), "seq": n, "pid": os.getpid(), "hook": name,
               "keys": {k: _summ(v) for k, v in kw.items()},
               "ids": {k: kw[k] for k in _ID_KEYS if k in kw and isinstance(kw[k], (str, int, bool, type(None)))}}
        try:
            with open(os.environ.get("HOOKDUMP_FILE", "/tmp/hookdump.jsonl"), "a") as f:
                f.write(json.dumps(row, default=str) + "\n")
        except Exception:
            pass
        return None
    cb.__name__ = f"hookdump_{name}"
    return cb

def register(ctx):
    from hermes_cli.plugins import VALID_HOOKS
    for h in sorted(VALID_HOOKS):
        ctx.register_hook(h, _make(h))
