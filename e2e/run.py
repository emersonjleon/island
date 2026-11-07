"""Run the browser smoke tests against real servers.

Needs Redis (REDIS_URL, default redis://127.0.0.1:6379/0), a built frontend
(``npm run build`` in frontend/) and Playwright with Chromium for Node.

    python e2e/run.py [--out DIR] [--port 8765]

It creates a fresh e2e.sqlite3, starts ``runserver`` and ``run_gamehost`` with
e2e/settings.py, runs e2e/two_player.cjs (two desktop browsers), e2e/phone.cjs
(a desktop against a touch-screen phone) and e2e/bots.cjs (one person against two
computer players) and stops both servers again.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ("two_player.cjs", "phone.cjs", "bots.cjs")
READY_TIMEOUT_S = 30


def wait_ready(url: str) -> None:
    deadline = time.monotonic() + READY_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as res:
                if res.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.5)
    raise SystemExit(f"server not ready at {url}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "e2e" / "out")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    env = {**os.environ, "DJANGO_SETTINGS_MODULE": "e2e.settings", "PYTHONUNBUFFERED": "1"}
    env.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
    (ROOT / "e2e.sqlite3").unlink(missing_ok=True)
    py = sys.executable
    subprocess.run([py, "manage.py", "migrate", "-v0"], cwd=ROOT, env=env, check=True)

    base = f"http://127.0.0.1:{args.port}"
    procs: list[tuple[str, subprocess.Popen]] = []
    try:
        for name, cmd in (("web", ["runserver", f"127.0.0.1:{args.port}", "--noreload"]), ("gamehost", ["run_gamehost"])):
            logf = open(args.out / f"{name}.log", "w")
            procs.append((name, subprocess.Popen([py, "manage.py", *cmd], cwd=ROOT, env=env, stdout=logf, stderr=subprocess.STDOUT)))
        started = time.monotonic()
        wait_ready(f"{base}/accounts/login/")
        print(f"servers ready in {time.monotonic() - started:.1f} s", flush=True)
        failed = 0
        for script in SCRIPTS:
            result = subprocess.run(["node", str(ROOT / "e2e" / script), base, str(args.out)], cwd=ROOT, env=env)
            failed += result.returncode != 0
        return 1 if failed else 0
    finally:
        for _, p in procs:
            p.terminate()
        for name, p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    sys.exit(main())
