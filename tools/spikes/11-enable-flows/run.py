#!/usr/bin/env python
"""Spike 11a: `hermes plugins install <local git repo>` in a temp HERMES_HOME; capture the
'Enable now? [y/N]' prompt and what n / y / --enable / --no-enable leave in config.yaml,
then `hermes plugins enable|disable`. Also builds a UNIFIED scratch package (agent + desktop/plugin.js).
Usage: run.py [OUTDIR]"""
import sys, os, subprocess, tempfile, textwrap, time, re
import pexpect

HERMES = os.path.expanduser("~/.local/bin/hermes")
out = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="cf11-out-")
os.makedirs(out, exist_ok=True)
log = open(f"{out}/11a.log", "w")

def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True); log.write(s + "\n"); log.flush()

def mk_repo(name):
    d = tempfile.mkdtemp(prefix=f"cf11-repo-{name}-")
    open(f"{d}/plugin.yaml", "w").write(f"name: {name}\nversion: '0.0.1'\ndescription: scratch unified package\n")
    open(f"{d}/__init__.py", "w").write("def register(ctx):\n    pass\n")
    os.makedirs(f"{d}/desktop")
    open(f"{d}/desktop/plugin.js", "w").write("export default { id: '%s', register() {} }\n" % name)
    for c in ("git init -q -b main", "git add -A", "git -c user.email=a@b -c user.name=x commit -q -m init"):
        subprocess.run(c, shell=True, cwd=d, check=True)
    return d

def env(home):
    e = dict(os.environ)
    for k in list(e):
        if k.startswith("HERMES_"): e.pop(k)
    e.update(HOME="/home/adam", HERMES_HOME=home, TERM="xterm")
    return e

def cfg(home):
    p = f"{home}/config.yaml"
    txt = open(p).read() if os.path.exists(p) else "<no config.yaml>"
    m = re.search(r"^plugins:.*?(?=^\S|\Z)", txt, re.S | re.M)
    return m.group(0).strip() if m else "<no plugins: block>"

def run(home, args, answer=None):
    say(f"\n$ HERMES_HOME={home} hermes {' '.join(args)}   [answer={answer!r}]")
    p = pexpect.spawn(HERMES, args, env=env(home), timeout=120, encoding="utf-8")
    buf = ""
    if answer is not None:
        i = p.expect([r"\[y/N\]:", pexpect.EOF, pexpect.TIMEOUT])
        buf += p.before + (p.after if isinstance(p.after, str) else "")
        if i == 0:
            p.sendline(answer)
    p.expect(pexpect.EOF); buf += p.before
    p.close()
    buf = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", buf)
    if args[:2] == ["plugins", "list"]:
        buf = "\n".join(l for l in buf.splitlines() if "scratch-" in l or "Status" in l)
    say(buf.strip()); say(f"[exit={p.exitstatus}]")
    say(f"--- config plugins block after: {cfg(home)}")

for tag, answer, extra in (("decline-n", "n", []), ("accept-y", "y", []), ("default-enter", "", []),
                           ("flag-enable", None, ["--enable"]), ("flag-no-enable", None, ["--no-enable"])):
    home = tempfile.mkdtemp(prefix="cf11-home-")
    repo = mk_repo(f"scratch-{tag}")
    say(f"\n=========== {tag} (home={home}, repo={repo})")
    run(home, ["plugins", "install", f"file://{repo}", *extra], answer)
    run(home, ["plugins", "list"])
    if tag == "decline-n":
        run(home, ["plugins", "enable", f"scratch-{tag}"])
        run(home, ["plugins", "disable", f"scratch-{tag}"])
        run(home, ["plugins", "list"])
    say("plugin dir:", subprocess.run(f"ls -a {home}/plugins/scratch-{tag}", shell=True, capture_output=True, text=True).stdout.split())
say("\nDONE")
