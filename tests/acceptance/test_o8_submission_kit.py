"""ACCEPTANCE CONTRACT — O8: the submission kit, ready for Adam to press the buttons (locked).

Kit dir: CF_KIT_DIR (default: the vault's hermes-hackathon-2611/cuttlefish/kit). The catalog entry is ALSO a commit on
branch `catalog/cuttlefish-theme` of the local hermes-agent clone (CF_HERMES_CORE) and must NOT be on any remote.
Field set copied from a merged precedent: plugin-catalog/wallpaper-theme.yaml at v0.22.7.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from .helpers import CORE, ROOT

KIT = Path(os.environ.get("CF_KIT_DIR", "/home/adam/obsidian-vault/projects/hermes-hackathon-2611/cuttlefish/kit"))
TAG = "v2.0.0"
BRANCH = "catalog/cuttlefish-theme"
REPO_URL = "https://github.com/wisechef-ai/cuttlefish-theme"
# The newest core features the plugin relies on, by the commit that ADDED each file (verified at v0.22.7).
FEATURE_FILES = ["apps/desktop/src/lib/budgeted-loop.ts", "apps/desktop/src/lib/session-row-slots.ts",
                 "hermes_cli/plugin_events.py", "hermes_cli/plugin_validate_desktop.py"]


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture(scope="module")
def entry() -> dict:
    p = KIT / "catalog" / "cuttlefish-theme.yaml"
    assert p.is_file(), f"{p} missing"
    return yaml.safe_load(p.read_text())


def test_O8_1_catalog_entry_pins_the_tag(entry):
    tag_sha = git(ROOT, "rev-parse", f"{TAG}^{{commit}}")
    manifest = yaml.safe_load(git(ROOT, "show", f"{TAG}:plugin.yaml"))
    assert entry["name"] == "cuttlefish-theme" and entry["repo"] == REPO_URL
    assert re.fullmatch(r"[0-9a-f]{40}", entry["sha"]) and entry["sha"] == tag_sha, "exact 40-char sha of the tag"
    assert str(entry["version"]) == str(manifest["version"]) == TAG.lstrip("v")
    assert entry["tier"] == "community" and entry["category"] == "desktop"
    assert entry["requires_hermes"] == manifest["requires_hermes"]
    caps = entry["capabilities"]
    assert sorted(caps["provides_hooks"]) == sorted(manifest["provides_hooks"])
    assert caps["provides_tools"] == [] and caps["provides_middleware"] == []
    assert "Disclosure" in entry["description"], "rule 13: an explicit Disclosure sentence"
    for word in ("plugin_api.py", "No network", "skin"):
        assert word.lower() in entry["description"].lower(), f"disclosure must cover: {word}"
    for url in entry.get("screenshots", []):
        assert url.startswith(f"https://raw.githubusercontent.com/wisechef-ai/cuttlefish-theme/{tag_sha}/"), url
    assert 1 <= len(entry.get("screenshots", [])) <= 6


def test_O8_2_requires_hermes_floor_is_true(entry):
    floor = re.fullmatch(r">=(\d+\.\d+\.\d+)", entry["requires_hermes"])
    assert floor, entry["requires_hermes"]
    tag = f"v{floor.group(1)}"
    assert git(CORE, "tag", "-l", tag) == tag, f"{tag} is not a Hermes release tag"
    latest = "v0.22.7"
    assert tuple(map(int, floor.group(1).split("."))) <= tuple(map(int, latest[1:].split("."))), "floor ≤ latest release"
    for f in FEATURE_FILES:
        added = git(CORE, "log", "--diff-filter=A", "--format=%H", latest, "--", f).splitlines()[-1]
        contains = git(CORE, "tag", "--contains", added).split()
        assert tag in contains, f"{f} (added in {added[:11]}) is not in {tag}: the floor is untruthful"


def test_O8_3_catalog_commit_on_a_local_branch_not_pushed(entry):
    head = git(CORE, "rev-parse", BRANCH)
    files = git(CORE, "show", "--name-only", "--format=", head).split()
    assert files == ["plugin-catalog/cuttlefish-theme.yaml"], files
    assert yaml.safe_load(git(CORE, "show", f"{head}:plugin-catalog/cuttlefish-theme.yaml")) == entry
    assert git(CORE, "branch", "-r", "--contains", head) == "", "the catalog branch must not be on any remote"


def test_O8_4_pr_body(entry):
    body = (KIT / "PR-BODY.md").read_text()
    for section in ("## What", "## Surfaces", "## Disclosure", "## Screenshots", "## How to test"):
        assert section in body, section
    assert entry["sha"] in body and TAG in body
    assert "hermes plugins validate" in body
    assert re.search(r"no network", body, re.I)


def test_O8_5_demo_video_and_opener():
    video = KIT / "video" / "cuttlefish-v2-demo.mp4"
    assert video.is_file()
    if not shutil.which("ffprobe"):
        pytest.fail("ffprobe is needed to measure the demo")
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                             capture_output=True, text=True, check=True).stdout.strip())
    assert 60 <= d <= 75, f"demo is {d:.1f} s (60–75 s)"
    srt = (KIT / "video" / "captions.srt").read_text()
    first = re.search(r"(\d\d):(\d\d):(\d\d),(\d{3}) -->.*?\n(.+?)\n\n", srt, re.S)
    assert first, "captions.srt has cues"
    start = int(first.group(1)) * 3600 + int(first.group(2)) * 60 + int(first.group(3)) + int(first.group(4)) / 1000
    assert start <= 1.0 and "learn the language in 10 seconds" in first.group(5).lower(), "the opener"


def test_O8_6_x_post_is_hook_first_labelled_and_claim_grounded():
    post = (KIT / "x-post.md").read_text().strip()
    lines = [ln for ln in post.splitlines() if ln.strip()]
    assert len(lines[0]) <= 140, "hook-first: the first line stands alone"
    assert re.search(r"\bAI[- ]assisted\b|\bmade with AI\b|#AIgenerated", post, re.I), "AI-content label (governance)"
    claims = json.loads((KIT / "x-claims.json").read_text())["claims"]
    numbers = set(re.findall(r"\d+(?:\.\d+)?", post))
    grounded = set()
    for c in claims:
        ev = Path(c["evidence"])
        ev = ev if ev.is_absolute() else ROOT / ev
        assert ev.is_file(), f"claim {c['text']!r}: evidence {c['evidence']} missing"
        grounded |= set(re.findall(r"\d+(?:\.\d+)?", c["text"]))
    assert numbers <= grounded | {"2", "0", "10"}, f"ungrounded numbers in the post: {sorted(numbers - grounded)}"
