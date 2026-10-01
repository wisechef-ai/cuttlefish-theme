#!/usr/bin/env python3
"""cf2909 P1 (lane H): render the FULL CONTRACT §4 matrix of one or more direction modules through the
REAL hosts and write manifest.json per direction.

    python3 tools/p1/capture_matrix.py --direction design/directions/<id> [--direction ...] \\
        --out <vault>/projects/cuttlefish-theme/p1/renders/

Hosts (every capture comes from a running Hermes process; browser mockups never count):
  tui-terminator   the real `hermes --tui` (installed dist, read-only) in Terminator on a PRIVATE Xvfb
                   (default :95; :0/:1 are refused), via tools/capture_tui.py --mode terminator --sequence.
                   One TUI launch per grid/depth serves every scene of every direction (scene file + ack).
  tui-pane-webgl / tui-pane-dom
                   the same TUI inside the real desktop app's terminal pane (xterm.js), bg rung, both renderers
                   (spike-12 capture-desktop-pane pattern), via tools/p1/hosts/desktop-capture.ts.
  desktop          the real desktop app with the stub plugin "Cuttlefish" enabled through the user's consent path
                   (Capabilities ▸ Plugins ▸ Installed ▸ card ▸ Desktop: Cuttlefish); field pane (XL), status chip (M),
                   session-row swatch (S) + a 20-row sidebar.
  --backend virtual swaps Terminator for the pty+pyte backend (no X, CI) and skips the desktop hosts.

Each manifest entry carries a capture_log: the command line, `ps` of the host process tree taken at the
instant of capture, both SHAs, the throwaway HERMES_HOME and the host's own ack of the scene it drew.
Exit 0 when every required entry was captured, 1 otherwise (the manifest is still written, with `missing`).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
ROOT = TOOLS.parent
FIXTURE = HERE / "stub-sessions.json"
WIDGET = HERE / "hosts" / "tui-stub-widget.mjs"
DESKTOP_PLUGIN = HERE / "hosts" / "desktop-stub" / "plugin.js"
DESKTOP_CAPTURE = HERE / "hosts" / "desktop-capture.ts"
LAUNCH_TUI = TOOLS / "spikes" / "12-terminal-rendering-real-tui" / "launch-tui.sh"
CAPTURE_TUI = TOOLS / "capture_tui.py"
SCHEMA = "cf2909.p1.manifest/1"
STATES = ("idle", "working", "review", "needs-you", "fault", "unknown")
WORKING_T = (0.0, 0.25, 0.5, 0.75)
STATIC_T = (0.0, 0.5)            # two DIFFERENT t: identical pixels prove the state is static (D1)
RUNTIMES = {"installed": Path.home() / ".hermes" / "hermes-agent",
            "upstream": Path.home() / ".worktrees" / "hermes-agent" / "cf2909-upstream"}
TUI_CONFIG = ("model:\n  default: stub\n  provider: custom\n  base_url: http://127.0.0.1:9/v1\n  api_key: stub\n"
              "display:\n  interface: tui\n")

sys.path.insert(0, str(TOOLS))
import capture_tui as ct  # noqa: E402


# =========================================================================== pure planning

def frames_for(state: str) -> tuple[float, ...]:
    return WORKING_T if state == "working" else STATIC_T


def first_session_in(fixture: dict, state: str) -> int:
    return next(s["idx"] for s in fixture["sessions"] if s["state"] == state)


def tname(t: float) -> str:
    return f"t{int(round(t * 100)):03d}"


def plan_entries(fixture: dict, hosts: set[str]) -> list[dict]:
    """Every CONTRACT §4 entry for ONE direction, as dicts with an `id`, a `scene` (what the host must draw)
    and the manifest fields. `hosts` selects tui / pane / desktop (the virtual backend runs tui only)."""
    out: list[dict] = []
    looks = [(st, first_session_in(fixture, st), False) for st in STATES] + [("unknown", None, True)]

    def look_name(st, degraded):
        return "degraded" if degraded else st

    if "tui" in hosts:
        for depth, cols, dtag in (("truecolor", 120, "tc"), ("256", 120, "256"), ("truecolor", 80, "tc")):
            for st, idx, deg in looks:
                for t in frames_for(st):
                    name = f"M-half-{dtag}-{cols}-{look_name(st, deg)}-{tname(t)}"
                    out.append(dict(id=name, file=f"tui/{name}.png", host="tui-terminator", scale="M", state=st,
                                    degraded=deg, rung="half", depth=depth, cols=cols, session_idx=idx,
                                    sessions=[] if deg else [idx], frame_t=t, launch=f"term-{dtag}-{cols}",
                                    scene=dict(view="degraded" if deg else "mantle", state=st, session_idx=idx or 0,
                                               frame_t=t, rung="half", depth=depth, mantle_rows=2)))
        for st in STATES:
            idx = first_session_in(fixture, st)
            for t in frames_for(st):
                name = f"S-pill-half-tc-120-{st}-{tname(t)}"
                out.append(dict(id=name, file=f"tui/{name}.png", host="tui-terminator", scale="S", state=st,
                                degraded=False, rung="half", depth="truecolor", cols=120, session_idx=idx,
                                sessions=[idx], frame_t=t, launch="term-tc-120",
                                scene=dict(view="pill", state=st, session_idx=idx, frame_t=t, rung="half",
                                           depth="truecolor")))
        for n in (16, 20):
            for t in STATIC_T:
                name = f"S-grid{n}-half-tc-120-idle-{tname(t)}"
                out.append(dict(id=name, file=f"tui/{name}.png", host="tui-terminator", scale="S", state="idle",
                                degraded=False, rung="half", depth="truecolor", cols=120, session_idx=None,
                                sessions=list(range(n)), frame_t=t, launch="term-tc-120", grid=n,
                                scene=dict(view=f"grid{n}", state="idle", session_idx=0, frame_t=t, rung="half",
                                           depth="truecolor")))
    if "pane" in hosts:
        for renderer in ("webgl", "dom"):
            for st, idx, deg in looks:
                for t in frames_for(st):
                    name = f"M-bg-{renderer}-120-{look_name(st, deg)}-{tname(t)}"
                    out.append(dict(id=name, file=f"tui/{name}.png", host=f"tui-pane-{renderer}", scale="M", state=st,
                                    degraded=deg, rung="bg", depth="truecolor", cols=120, session_idx=idx,
                                    sessions=[] if deg else [idx], frame_t=t, launch=f"desk-{renderer}",
                                    scene=dict(view="degraded" if deg else "mantle", state=st, session_idx=idx or 0,
                                               frame_t=t, rung="bg", depth="truecolor", mantle_rows=2)))
    if "desktop" in hosts:
        for st, idx, deg in looks:
            for t in frames_for(st):
                shot = f"desktop-{look_name(st, deg)}-{tname(t)}"
                for scale in ("XL", "M", "S"):
                    name = f"{scale}-desktop-{look_name(st, deg)}-{tname(t)}"
                    out.append(dict(id=name, file=f"desktop/{shot}.png", host="desktop", scale=scale, state=st,
                                    degraded=deg, rung="dom", depth="truecolor", cols=None,
                                    session_idx=None if deg else idx, sessions=[] if deg else [idx], frame_t=t,
                                    launch="desk-dom", shot=shot,
                                    target={"XL": "field", "M": "chip", "S": "swatch"}[scale],
                                    scene=dict(state=st, session_idx=idx if idx is not None else 0, degraded=deg,
                                               frame_t=t)))
        for t in STATIC_T:
            name = f"S-desktop-sidebar20-idle-{tname(t)}"
            out.append(dict(id=name, file=f"desktop/sidebar20-idle-{tname(t)}.png", host="desktop", scale="S",
                            state="idle", degraded=False, rung="dom", depth="truecolor", cols=None, session_idx=None,
                            sessions=list(range(20)), frame_t=t, launch="desk-dom", shot=f"sidebar20-idle-{tname(t)}",
                            target="sidebar", grid=20,
                            scene=dict(state="idle", session_idx=-1, rowState="idle", degraded=False, frame_t=t)))
    return out


MANIFEST_KEYS = ("file", "host", "scale", "state", "rung", "depth", "cols", "session_idx", "sessions", "frame_t",
                 "crop", "capture_log")


def manifest_entry(e: dict) -> dict:
    m = {k: e.get(k) for k in MANIFEST_KEYS}
    m["degraded"] = bool(e.get("degraded"))
    if e.get("tiles") is not None:
        m["tiles"] = e["tiles"]
    return m


# --------------------------------------------------------------------------- crops (pure, tested)

def tui_box_cells(model: "ct.ScreenModel", box_rows: int) -> tuple[int, int, int, int] | None:
    """The widget's dock box in CELLS (col, row, w, h): the `box_rows` rows directly above the composer `❯`,
    spanning every cell with a non-default background (pixel cells always carry one)."""
    lines = model.screen.display
    prompt = max((y for y, line in enumerate(lines) if line.lstrip().startswith("❯")), default=None)
    if prompt is None or prompt - box_rows < 0:
        return None
    r0 = prompt - box_rows
    xs = [x for y in range(r0, prompt) for x in range(model.screen.columns) if model.cell(x, y).bg != "default"]
    if not xs:
        return None
    return (min(xs), r0, max(xs) - min(xs) + 1, box_rows)


def palette_bbox(png: Path, palette: set[tuple[int, int, int]], min_frac: float = 0.5):
    """Pixel bbox (x, y, w, h) of the band whose rows are ≥ min_frac palette colours (the full-width mantle)."""
    from PIL import Image
    im = Image.open(png).convert("RGB")
    w, h = im.size
    px = im.load()
    rows = [y for y in range(h) if sum(px[x, y] in palette for x in range(w)) >= w * min_frac]
    if not rows:
        return None
    y0, y1 = rows[0], rows[-1]
    xs = [x for y in rows for x in range(w) if px[x, y] in palette]
    return (min(xs), y0, max(xs) - min(xs) + 1, y1 - y0 + 1)


def calibrate(cell_box: tuple[int, int, int, int], px_box: tuple[int, int, int, int]) -> tuple[float, float, float, float]:
    """(ox, oy, cell_w, cell_h) of a terminal screenshot from one box known in both cells and pixels."""
    c, r, cw, ch = cell_box
    x, y, w, h = px_box
    cell_w, cell_h = w / cw, h / ch
    return (x - c * cell_w, y - r * cell_h, cell_w, cell_h)


def cells_to_px(cal, cell_box) -> list[int]:
    ox, oy, cw, chh = cal
    c, r, w, h = cell_box
    return [round(ox + c * cw), round(oy + r * chh), round(w * cw), round(h * chh)]


def palette_fraction(png: Path, crop, palette: set[tuple[int, int, int]]) -> float:
    """Share of the crop's pixels that are colours the host says it painted (sampled every 2nd px)."""
    from PIL import Image
    im = Image.open(png).convert("RGB")
    x, y, w, h = crop
    px = im.load()
    pts = [(xx, yy) for yy in range(y, y + h, 2) for xx in range(x, x + w, 2)
           if 0 <= xx < im.width and 0 <= yy < im.height]
    return sum(px[p] in palette for p in pts) / max(1, len(pts))


MIN_PALETTE_FRACTION = 0.5   # a crop that is mostly NOT the box's colours is in the wrong place: entry → missing


def hex_rgb(h: str) -> tuple[int, int, int]:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


# =========================================================================== I/O shell

def log(msg: str) -> None:
    print(f"[capture_matrix {dt.datetime.now():%H:%M:%S}] {msg}", file=sys.stderr, flush=True)


def git_sha(path: Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(path), "rev-parse", "--short=11", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def direction_meta(path: Path, node: str) -> dict:
    code = ("import(process.argv[1]).then(m => { if (typeof m.paint !== 'function') throw new Error('no paint'); "
            "console.log(JSON.stringify(m.meta ?? null)) })")
    r = subprocess.run([node, "--input-type=module", "-e", code, path.resolve().as_uri()], capture_output=True,
                       text=True, timeout=60)
    if r.returncode:
        raise SystemExit(f"capture_matrix: cannot load {path}: {r.stderr.strip()}")
    meta = json.loads(r.stdout)
    if not meta or meta.get("id") != path.parent.name:
        raise SystemExit(f"capture_matrix: {path}: meta.id must equal the directory name {path.parent.name!r}")
    return meta


def inline_directions(directions: dict[str, Path], fixture: dict) -> str:
    """The desktop loader resolves only @hermes/plugin-sdk / react* (blob: base), so directions are inlined.
    They are pure no-import ESM (CONTRACT §2): stripping `export` and returning the bindings is exact."""
    parts = []
    for did, path in directions.items():
        src = path.read_text(encoding="utf-8")
        if re.search(r"^\s*import\b", src, re.M):
            raise SystemExit(f"capture_matrix: {path} has an import; CONTRACT §2 forbids imports")
        names = re.findall(r"^export\s+(?:const|let|function)\s+([A-Za-z_$][\w$]*)", src, re.M)
        body = re.sub(r"^export\s+(?=const|let|function)", "", src, flags=re.M)
        body = re.sub(r"^export\s*\{[^}]*\};?\s*$", "", body, flags=re.M)
        ret = ", ".join(names)
        parts.append(f"  {json.dumps(did)}: (() => {{\n{body}\n  return {{ {ret} }}\n  }})(),")
    return ("const DIRECTIONS = {\n" + "\n".join(parts) + "\n}\n"
            f"const FIXTURE = {json.dumps(fixture)}\n")


def build_desktop_package(dest: Path, directions: dict[str, Path], fixture: dict) -> Path:
    src = DESKTOP_PLUGIN.read_text(encoding="utf-8")
    begin, end = "/*__CF_P1_INLINE_BEGIN__*/", "/*__CF_P1_INLINE_END__*/"
    a, b = src.index(begin), src.index(end) + len(end)
    plugin = src[:a] + begin + "\n" + inline_directions(directions, fixture) + end + src[b:]
    (dest / "desktop").mkdir(parents=True, exist_ok=True)
    (dest / "desktop" / "plugin.js").write_text(plugin, encoding="utf-8")
    (dest / "plugin.yaml").write_text('name: cuttlefish\nversion: 0.0.0-p1stub\ndescription: "cf2909 P1 host stub '
                                      '(tools/p1/hosts). Not the product."\nauthor: "cuttlefish-theme tools"\n')
    (dest / "__init__.py").write_text("def register(ctx):\n    return None\n")
    return dest


def ensure_display(display: str) -> subprocess.Popen | None:
    if display in (":0", ":1"):
        raise SystemExit(f"capture_matrix: refusing DISPLAY={display} (a live desktop); use a private Xvfb")
    if Path(f"/tmp/.X11-unix/X{display.lstrip(':')}").exists():
        return None
    xvfb = ct._xvfb_binary()
    if not xvfb:
        raise SystemExit("capture_matrix: no Xvfb found")
    proc = subprocess.Popen([xvfb, display, "-screen", "0", "2800x2400x24", "-nolisten", "tcp"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(50):
        if Path(f"/tmp/.X11-unix/X{display.lstrip(':')}").exists():
            return proc
        time.sleep(0.1)
    raise SystemExit(f"capture_matrix: Xvfb {display} did not come up")


def make_tui_home(base: Path) -> Path:
    home = Path(tempfile.mkdtemp(prefix="cf-p1h-tui-", dir=base))
    (home / "tui-widgets").mkdir()
    shutil.copy(WIDGET, home / "tui-widgets" / "cfp1stub.mjs")
    (home / "config.yaml").write_text(TUI_CONFIG)
    return home


def write_capture_log(path: Path, *, command: str, ps: str, shas: dict, hermes_home: str, ack, extra: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# cf2909 P1 capture log ({dt.datetime.now().astimezone().isoformat(timespec='seconds')})",
             f"command: {command}", f"hermes_sha: {shas['hermes']}", f"plugin_sha: {shas['plugin']}",
             f"hermes_home: {hermes_home}"]
    lines += [f"{k}: {json.dumps(v) if not isinstance(v, str) else v}" for k, v in extra.items()]
    lines += ["ack: " + json.dumps(ack), "ps (host process tree at capture):", ps.rstrip(), ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_tui_launch(launch: str, items: list[tuple[str, dict]], args, ctx) -> None:
    """One `hermes --tui` launch, every (direction, entry) of this launch as one --sequence step."""
    m = re.fullmatch(r"term-(tc|256)-(\d+)", launch)
    dtag, cols = m.group(1), int(m.group(2))
    work = ctx["work"] / launch
    work.mkdir(parents=True, exist_ok=True)
    home = make_tui_home(ctx["work"])
    scene_path, ack_path = work / "scene.json", work / "ack.json"
    first_dir = ctx["directions"][items[0][0]]
    seq0 = ctx["next_seq"]()
    ct.write_atomic(scene_path, json.dumps(dict(items[0][1]["scene"], seq=seq0, direction=str(first_dir))))
    steps = []
    for did, e in items:
        seq = ctx["next_seq"]()
        e["_seq"], e["_work"] = seq, work
        out = ctx["out"][did]
        steps.append({"png": str(out / e["file"]), "raw_log": str(work / f"{did}--{e['id']}.sgr"),
                      "ps_log": str(work / f"{did}--{e['id']}.ps"), "ack_out": str(work / f"{did}--{e['id']}.ack.json"),
                      "wait_for": "❯", "settle": 0.4, "stable": "^\\s*❯",
                      "write": {"path": str(scene_path),
                                "text": json.dumps(dict(e["scene"], seq=seq, direction=str(ctx["directions"][did])))},
                      "ack": {"path": str(ack_path), "seq": seq}})
    (work / "sequence.json").write_text(json.dumps(steps))
    cmd = [sys.executable, str(CAPTURE_TUI), "--mode", args.backend, "--display", args.display,
           "--wait-for", "❯", "--timeout", "180", "--settle", "1", "--cols", str(cols), "--rows", "40",
           "--png", str(work / "first.png"), "--raw-log", str(work / "first.sgr"), "--sequence", str(work / "sequence.json"),
           "--env", f"CF_P1_DIRECTION={first_dir}", "--env", f"CF_P1_FIXTURE={FIXTURE}",
           "--env", f"CF_P1_SCENE={scene_path}", "--env", f"CF_P1_ACK={ack_path}",
           "--env", f"CF_HERMES_SRC={ctx['checkout']}"]
    if dtag == "256":
        cmd.append("--no-colorterm")
    cmd += ["--", "bash", str(LAUNCH_TUI)]
    env = dict(os.environ, HERMES_HOME=str(home), HOME=str(Path.home()))
    t0 = time.monotonic()
    log(f"{launch}: {len(steps)} shots, HERMES_HOME={home}")
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    ctx["timings"][launch] = round(time.monotonic() - t0, 1)
    (work / "capture_tui.out").write_text(r.stdout + "\n--- stderr\n" + r.stderr)
    if r.returncode:
        log(f"{launch}: capture_tui exit {r.returncode}: {r.stderr.strip()[-600:]}")
    command = shlex.join(cmd)
    cal = None
    for did, e in items:
        png, raw = ctx["out"][did] / e["file"], work / f"{did}--{e['id']}.sgr"
        ackf, psf = work / f"{did}--{e['id']}.ack.json", work / f"{did}--{e['id']}.ps"
        if not (png.exists() and raw.exists() and ackf.exists()):
            continue
        ack = json.loads(ackf.read_text())
        if ack.get("seq") != e["_seq"] or ack.get("cols") != cols:
            continue  # not the scene we asked for, or the terminal grid drifted: the entry stays missing
        payload, dims = ct.parse_script_log(raw.read_bytes())
        model = ct.model_from_bytes(payload, *(dims or (cols, 40)))
        cells = tui_box_cells(model, ack["cells"][1])
        if cells and args.backend == "virtual":
            cal = (0.0, 0.0, float(ct.CELL_W), float(ct.CELL_H))
        elif cells and (cal is None) and e["scene"]["view"] in ("mantle", "degraded"):
            pal = {hex_rgb(c) for c in ack.get("palette", [])}
            pb = palette_bbox(png, pal) if pal else None
            if pb:
                cal = calibrate(cells, pb)
        e["_cells"], e["_cal_needed"] = cells, cal is None
        e["_ack"] = ack
        e["_cmd"], e["_ps"], e["_home"] = command, psf.read_text() if psf.exists() else "", str(home)
    for did, e in items:
        if e.get("_cells") and cal:
            crop = cells_to_px(cal, e["_cells"])
            pal = {hex_rgb(c) for c in e["_ack"].get("palette", [])}
            frac = palette_fraction(ctx["out"][did] / e["file"], crop, pal)
            if frac < MIN_PALETTE_FRACTION:
                log(f"{did}/{e['id']}: crop {crop} is only {frac:.0%} box colours; entry left missing")
                continue
            e["crop"] = crop
            if e.get("grid"):
                ox, oy = e["_cells"][0], e["_cells"][1]
                e["tiles"] = [{"session_idx": t["session_idx"],
                               "crop": cells_to_px(cal, (ox + t["col"], oy + t["row"], t["w"], t["h"]))}
                              for t in e["_ack"].get("tiles", [])]
    if not args.keep:
        shutil.rmtree(home, ignore_errors=True)


def run_desktop_launch(renderer: str, entries: list[tuple[str, dict]], args, ctx) -> None:
    work = ctx["work"] / f"desk-{renderer}"
    work.mkdir(parents=True, exist_ok=True)
    desk = [(d, e) for d, e in entries if e["host"] == "desktop"]
    pane = [(d, e) for d, e in entries if e["host"].startswith("tui-pane-")]
    job: dict = {"runtime": args.runtime, "display": args.display, "gpu": renderer == "webgl",
                 "width": 2700, "height": 2380, "plugin_name": "Cuttlefish", "result": str(work / "result.json"),
                 "keep": args.keep}
    if desk:
        pkg = build_desktop_package(work / "package", ctx["directions"], ctx["fixture"])
        job["package"] = str(pkg)
        job["seed"] = {"python": ctx["backend_python"], "script": str(HERE / "seed_sessions.py"),
                       "checkout": str(ctx["checkout"])}
        shots: dict[tuple[str, str], dict] = {}
        for did, e in desk:
            key = (did, e["shot"])
            if key not in shots:
                seq = ctx["next_seq"]()
                shots[key] = {"scene": dict(e["scene"], seq=seq, direction=ctx["ids"][did]),
                              "file": str(ctx["out"][did] / e["file"]), "targets": []}
            e["_seq"] = shots[key]["scene"]["seq"]
            tgt = {"id": f"{did}--{e['id']}", "kind": e["target"]}
            if e["target"] == "swatch":
                tgt["idx"] = e["scene"]["session_idx"]
            shots[key]["targets"].append(tgt)
        job["desktop"] = list(shots.values())
    if pane:
        home = make_tui_home(ctx["work"])
        scene_path, ack_path = work / "pane-scene.json", work / "pane-ack.json"
        node = shutil.which("node") or "node"
        cmd = (f"HERMES_HOME={home} CF_NODE={node} CF_HERMES_SRC={ctx['checkout']} CF_P1_DIRECTION={ctx['directions'][pane[0][0]]} "
               f"CF_P1_FIXTURE={FIXTURE} CF_P1_SCENE={scene_path} CF_P1_ACK={ack_path} exec bash {LAUNCH_TUI}")
        shots_p = []
        for did, e in pane:
            seq = ctx["next_seq"]()
            e["_seq"], e["_home"] = seq, str(home)
            shots_p.append({"id": f"{did}--{e['id']}", "file": str(ctx["out"][did] / e["file"]),
                            "scene": dict(e["scene"], seq=seq, direction=str(ctx["directions"][did])),
                            "ack_out": str(work / f"{did}--{e['id']}.ack.json")})
        job["pane"] = {"tui_home": str(home), "scene_path": str(scene_path), "ack_path": str(ack_path), "cmd": cmd,
                       "cols": 120, "shots": shots_p}
    (work / "job.json").write_text(json.dumps(job, indent=1))
    node = shutil.which("node") or "node"
    cmd = [node, str(DESKTOP_CAPTURE), "--job", str(work / "job.json")]
    if shutil.which("systemd-run") and not os.environ.get("CF_NO_SCOPE"):
        cmd = ["systemd-run", "--user", "--scope", "-q", "-p", "MemoryMax=8G",
               "env", f"TMPDIR={os.environ.get('TMPDIR', '/tmp')}", f"CF_DISPLAY={args.display}"] + cmd
    t0 = time.monotonic()
    log(f"desk-{renderer}: {len(job.get('desktop', []))} desktop scenes + {len(pane)} pane shots")
    r = subprocess.run(cmd, cwd=str(TOOLS), capture_output=True, text=True)
    ctx["timings"][f"desk-{renderer}"] = round(time.monotonic() - t0, 1)
    (work / "desktop-capture.out").write_text(r.stdout + "\n--- stderr\n" + r.stderr)
    if r.returncode:
        log(f"desk-{renderer}: exit {r.returncode}: {(r.stderr or r.stdout).strip()[-800:]}")
    try:
        res = json.loads((work / "result.json").read_text())
    except (OSError, ValueError):
        log(f"desk-{renderer}: no result.json")
        return
    ctx["desktop_results"][renderer] = res
    by_id = {s["id"]: s for s in res.get("shots", [])}
    command = shlex.join(cmd) + f"   # electron: {res.get('command')}"
    for did, e in entries:
        s = by_id.get(f"{did}--{e['id']}")
        if not s:
            continue
        e["_ps"], e["_cmd"] = s["ps"], command
        e.setdefault("_home", res.get("hermes_home"))
        if e["host"] == "desktop":
            e["_home"] = res.get("hermes_home")
            e["_ack"] = {"seq": s["seq"], "renderer_ack": True}
            e["crop"] = s["crop"]
            if e.get("target") == "sidebar":
                e["tiles"] = s.get("tiles")
        else:
            ack = s.get("ack") or {}
            if ack.get("seq") != e["_seq"] or ack.get("cols") != e["cols"]:
                continue  # wrong scene or wrong grid (e.g. the pane did not reach 120 cols): stays missing
            e["_ack"] = ack
            pal = {hex_rgb(c) for c in ack.get("palette", [])}
            pb = palette_bbox(Path(s["file"]), pal) if pal else None
            e["crop"] = list(pb) if pb else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--direction", action="append", required=True, type=Path,
                    help="design/directions/<id> (repeatable: batched per host launch)")
    ap.add_argument("--out", required=True, type=Path, help="output root; one <direction-id>/ per direction")
    ap.add_argument("--runtime", default="installed", help="installed | upstream | <checkout path>")
    ap.add_argument("--display", default=":95", help="private Xvfb display (never :0/:1)")
    ap.add_argument("--backend", choices=("terminator", "virtual"), default="terminator",
                    help="TUI backend; virtual = pty+pyte, no X, desktop hosts skipped (CI)")
    ap.add_argument("--hosts", default="tui,pane,desktop", help="subset of tui,pane,desktop")
    ap.add_argument("--keep", action="store_true", help="keep throwaway homes and work files")
    args = ap.parse_args(argv)
    os.environ.setdefault("HOME", "/home/adam")

    hosts = {h.strip() for h in args.hosts.split(",") if h.strip()}
    if args.backend == "virtual":
        hosts &= {"tui"}
    checkout = RUNTIMES.get(args.runtime, Path(args.runtime)).resolve()
    if not (checkout / "ui-tui" / "dist" / "entry.js").exists():
        raise SystemExit(f"capture_matrix: no built TUI at {checkout}/ui-tui/dist (read-only launch needs the dist)")
    fixture = json.loads(FIXTURE.read_text())
    node = shutil.which("node") or "node"
    directions: dict[str, Path] = {}
    metas: dict[str, dict] = {}
    for d in args.direction:
        f = (d / "direction.mjs") if d.is_dir() else d
        meta = direction_meta(f, node)
        directions[meta["id"]] = f.resolve()
        metas[meta["id"]] = meta
    shas = {"hermes": git_sha(checkout), "plugin": git_sha(ROOT)}
    out = {did: (args.out / did).resolve() for did in directions}
    work = Path(tempfile.mkdtemp(prefix="cf-p1h-work-", dir=os.environ.get("TMPDIR")))
    seq = iter(range(1, 10**9))
    ctx = dict(directions=directions, ids={d: d for d in directions}, fixture=fixture, out=out, work=work,
               checkout=checkout, next_seq=lambda: next(seq), timings={}, desktop_results={})
    if "desktop" in hosts:
        r = subprocess.run([node, "--input-type=module", "-e",
                            "const h = await import(process.argv[1]); console.log(h.resolveBackendPython(process.argv[2]))",
                            (TOOLS / "desktop_harness.ts").as_uri(), str(checkout)], capture_output=True, text=True, cwd=TOOLS)
        if r.returncode:
            raise SystemExit(f"capture_matrix: cannot resolve the backend python: {r.stderr.strip()}")
        ctx["backend_python"] = r.stdout.strip()

    plans = {did: plan_entries(fixture, hosts) for did in directions}
    for did in directions:
        if out[did].exists():
            for sub in ("tui", "desktop", "logs"):
                shutil.rmtree(out[did] / sub, ignore_errors=True)
        out[did].mkdir(parents=True, exist_ok=True)

    xvfb = ensure_display(args.display) if (args.backend == "terminator" or hosts & {"pane", "desktop"}) else None
    t_start = time.monotonic()
    try:
        launches: dict[str, list[tuple[str, dict]]] = {}
        for did, entries in plans.items():
            for e in entries:
                launches.setdefault(e["launch"], []).append((did, e))
        for launch, items in launches.items():
            if launch.startswith("term-"):
                run_tui_launch(launch, items, args, ctx)
        for renderer in ("dom", "webgl"):
            items = launches.get(f"desk-{renderer}")
            if items:
                run_desktop_launch(renderer, items, args, ctx)
    finally:
        if xvfb:
            xvfb.terminate()
            try:
                xvfb.wait(timeout=5)
            except subprocess.TimeoutExpired:
                xvfb.kill()
    total = round(time.monotonic() - t_start, 1)

    rc = 0
    for did, entries in plans.items():
        good, missing = [], []
        for e in entries:
            png = out[did] / e["file"]
            if not (png.exists() and e.get("_ps") and e.get("_ack") is not None and e.get("crop")):
                missing.append(e["id"])
                continue
            logp = Path("logs") / f"{e['id']}.log"
            write_capture_log(out[did] / logp, command=e["_cmd"], ps=e["_ps"], shas=shas, hermes_home=e.get("_home") or "",
                              ack=e["_ack"], extra={"direction": did, "host": e["host"], "scene": e["scene"]})
            e["capture_log"] = str(logp)
            good.append(manifest_entry(e))
        manifest = {"schema": SCHEMA, "direction": did, "direction_meta": metas[did], "hermes_sha": shas["hermes"],
                    "plugin_sha": shas["plugin"], "runtime": str(checkout), "backend": args.backend,
                    "hosts": sorted(hosts), "created": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                    "timings_s": dict(ctx["timings"], total=total, directions=len(directions)),
                    "desktop": {r: {k: v for k, v in res.items() if k in ("boot_ms", "boot_total_ms", "total_ms", "enabled",
                                                                       "pane_grid", "pane_renderer", "sidebar_rows",
                                                                       "plugin", "errors", "sha")}
                                for r, res in ctx["desktop_results"].items()},
                    "entries": good, "missing": missing}
        (out[did] / "manifest.json").write_text(json.dumps(manifest, indent=1))
        log(f"{did}: {len(good)} entries, {len(missing)} missing → {out[did] / 'manifest.json'}")
        if missing:
            rc = 1
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    else:
        log(f"work dir kept: {work}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
