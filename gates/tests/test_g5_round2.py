"""Round-2 G5 instrument parts: OpenAI-compatible helper (fake transport), answer cache key, text-masking defaults, prompt blindness."""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import g5backends  # noqa: E402
import g5cache  # noqa: E402
import g5items  # noqa: E402

GATES = Path(__file__).resolve().parents[1]


class HTTPErr(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP Error {status}")
        self.status = status


def _ok(text):
    return {"choices": [{"message": {"content": text}}]}


@pytest.fixture
def png(tmp_path):
    p = tmp_path / "a.png"
    p.write_bytes(b"\x89PNG-fake")
    return p


def _call(post, png, sleeps, **kw):
    cfg = g5backends.OpenAICompat(url="http://x/v1/chat/completions", key_name="K", model="m", min_interval=kw.pop("min_interval", 0.0),
                                  max_retries=kw.pop("max_retries", 4), extra_body=kw.pop("extra_body", {}))
    return g5backends.openai_compat_call(cfg, png, "p", post=post, sleep=sleeps.append, key="k", rand=lambda: 0.0)


def test_helper_sends_image_prompt_model_and_extra_body(png):
    seen = {}

    def post(url, headers, body):
        seen.update(url=url, headers=headers, body=body)
        return _ok("hi")

    cfg = g5backends.OpenAICompat(url="http://x/v1/chat/completions", key_name="K", model="m", min_interval=0, extra_body={"chat_template_kwargs": {"enable_thinking": False}})
    assert g5backends.openai_compat_call(cfg, png, "PROMPT", post=post, sleep=lambda s: None, key="sek") == "hi"
    assert seen["headers"]["Authorization"] == "Bearer sek"
    assert seen["body"]["model"] == "m" and seen["body"]["chat_template_kwargs"] == {"enable_thinking": False}
    parts = seen["body"]["messages"][0]["content"]
    assert parts[0] == {"type": "text", "text": "PROMPT"} and parts[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_helper_retries_429_and_5xx_with_exponential_backoff_then_succeeds(png):
    results = [HTTPErr(429), HTTPErr(503), HTTPErr(429), _ok("done")]
    sleeps = []

    def post(url, headers, body):
        r = results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    assert _call(post, png, sleeps) == "done"
    assert len(sleeps) == 3 and sleeps[0] < sleeps[1] < sleeps[2]          # exponential
    assert sleeps[1] >= 2 * sleeps[0] * 0.99


def test_helper_gives_up_after_bounded_retries_with_a_transport_error(png):
    calls, sleeps = [], []

    def post(url, headers, body):
        calls.append(1)
        raise HTTPErr(429)

    with pytest.raises(g5backends.TransportError) as e:
        _call(post, png, sleeps, max_retries=3)
    assert len(calls) == 4 and "429" in str(e.value)                       # 1 try + 3 retries


def test_helper_does_not_retry_a_4xx_client_error(png):
    calls = []

    def post(url, headers, body):
        calls.append(1)
        raise HTTPErr(400)

    with pytest.raises(g5backends.TransportError):
        _call(post, png, [])
    assert len(calls) == 1


def test_helper_jitter_is_applied(png):
    sleeps, results = [], [HTTPErr(429), _ok("x")]

    def post(url, headers, body):
        r = results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    cfg = g5backends.OpenAICompat(url="u", key_name="K", model="m", min_interval=0)
    g5backends.openai_compat_call(cfg, png, "p", post=post, sleep=sleeps.append, key="k", rand=lambda: 1.0)
    assert sleeps[0] > g5backends.BACKOFF_BASE                              # base + jitter


def test_pacing_enforces_the_min_interval_between_calls(png):
    t = [100.0]
    sleeps = []
    pacer = g5backends.Pacer(clock=lambda: t[0], sleep=lambda s: (sleeps.append(s), t.__setitem__(0, t[0] + s)))
    pacer.wait(3.0)
    t[0] += 1.0
    pacer.wait(3.0)
    assert sleeps == [pytest.approx(2.0)]                                  # first call free, second waits the remaining 2 s


def test_backends_resolve_and_default_pair():
    assert g5backends.resolve("qwen") and g5backends.resolve("glm") and g5backends.resolve("codex")
    assert g5backends.resolve("nope") is None
    assert g5backends.DEFAULT_BACKENDS == "qwen,glm"


def test_model_ids_are_configurable_through_env(monkeypatch):
    monkeypatch.setenv("G5_QWEN_MODEL", "q-test")
    monkeypatch.setenv("G5_GLM_MODEL", "g-test")
    assert g5backends.model_id("qwen") == "q-test" and g5backends.model_id("glm") == "g-test"
    monkeypatch.delenv("G5_GLM_MODEL")
    assert g5backends.model_id("glm") == "glm-4.6v-flash"


# ---- cache ---------------------------------------------------------------------------------
def test_cache_key_depends_on_backend_model_image_and_prompt(png, tmp_path):
    base = g5cache.key("qwen", "m1", png, "prompt")
    other = tmp_path / "b.png"
    other.write_bytes(b"different")
    assert len({base, g5cache.key("glm", "m1", png, "prompt"), g5cache.key("qwen", "m2", png, "prompt"),
                g5cache.key("qwen", "m1", other, "prompt"), g5cache.key("qwen", "m1", png, "prompt2")}) == 5
    same_bytes = tmp_path / "renamed.png"
    same_bytes.write_bytes(png.read_bytes())
    assert g5cache.key("qwen", "m1", same_bytes, "prompt") == base          # content-addressed, not name-addressed
    assert re.fullmatch(r"[0-9a-f]{64}", base)


def test_cache_roundtrip_and_no_cache(tmp_path, png):
    c = g5cache.Cache(tmp_path / "c")
    k = g5cache.key("qwen", "m", png, "p")
    assert c.get(k) is None
    c.put(k, "RAW")
    assert c.get(k) == "RAW"
    assert g5cache.Cache(tmp_path / "c", enabled=False).get(k) is None     # --no-cache forces a fresh call


def test_wrap_serves_second_call_from_cache_and_never_caches_errors(tmp_path, png):
    c = g5cache.Cache(tmp_path / "c")
    calls = []

    def fn(p, prompt):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("429")
        return "ANSWER"

    w = g5cache.cached(fn, "qwen", "m", c)
    with pytest.raises(RuntimeError):
        w(png, "p")
    assert w(png, "p") == "ANSWER" and w.last_cached is False
    assert w(png, "p") == "ANSWER" and w.last_cached is True and len(calls) == 2


# ---- text masking defaults (D-R2-5) --------------------------------------------------------
def test_alarm_text_policy_defaults():
    assert g5items.keep_alarm_for(None, None) is True            # plain legend keeps alarm words
    for kind in ("deutan", "protan", "tritan"):
        assert g5items.keep_alarm_for(None, kind) is False       # CVD legends are pattern-only
    assert g5items.keep_alarm_for(True, "deutan") is True        # explicit override, informational
    assert g5items.keep_alarm_for(False, None) is False


# ---- prompt blindness audit ----------------------------------------------------------------
VOCAB = ("cuttlefish", "sepia", "chromatophore", "iridophore", "mantle", "passing cloud", "passing-cloud", "passingcloud",
         "deimatic", "zebra", "eyespot", "eye-spot", "eye spot", "a-chromatophore", "b-disruptive", "c-iridophore", "disruptive", "leucophore")
NEUTRAL_LABELS = {"idle", "working", "review", "needs input", "error", "unknown"}


def test_no_prompt_file_contains_design_vocabulary():
    files = sorted((GATES / "g5_prompts").glob("*.txt"))
    assert len(files) >= 4
    for f in files:
        text = f.read_text().lower()
        for w in VOCAB:
            assert w not in text, f"{f.name} leaks {w!r}"


def test_legend_labels_are_the_neutral_set_only():
    text = (GATES / "g5_prompts" / "legend.txt").read_text()
    m = re.search(r"\(([^)]*)\)", text)
    assert {s.strip() for s in m.group(1).split(",")} == NEUTRAL_LABELS
    m2 = re.search(r"one of: ([^>\"]*)>", text)
    assert {s.strip() for s in m2.group(1).split(",")} == NEUTRAL_LABELS
    assert "needs-you" not in text and "fault" not in text


def test_item_prompts_from_real_item_builders_are_clean(tmp_path):
    import dirtools
    import fixture_render
    import gatelib
    root = fixture_render.build(GATES / "tests" / "fixtures" / "good", tmp_path / "good")
    man, ddir = gatelib.load_manifest(root), dirtools.resolve_direction_dir("good")
    items = g5items.build_items(man, ddir, 1)
    assert len(items) > 50
    for pf in {i.prompt_file for i in items}:
        assert (g5items.PROMPTS / pf).is_file()
    for i in items:
        low = i.prompt.lower()
        assert not any(w in low for w in VOCAB), i.id
        assert i.id.split("-")[0] in ("aesthetic", "legend", "identity")
    from_ids = {i.prompt_file for i in items}
    assert from_ids <= {p.name for p in g5items.PROMPTS.glob("*.txt")}
