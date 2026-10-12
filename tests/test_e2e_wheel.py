"""End to end: build the wheel, install it in a fresh venv, use it as an outsider would."""

from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

CONSUMER = """
import asyncio, time
import taplimit
from taplimit import KeyedRateLimiter, RateLimiter, RateLimitExceeded, parse_rate, rate_limit

assert taplimit.__file__.find("site-packages") != -1, taplimit.__file__
limiter = RateLimiter(*parse_rate("2/0.2s"))
start = time.monotonic()
for _ in range(5):
    limiter.acquire()
assert time.monotonic() - start >= 0.4, "the limit was exceeded"

@rate_limit(1, 60, on_limit="raise")
def once() -> str:
    return "ok"

assert once() == "ok"
try:
    once()
except RateLimitExceeded as exc:
    assert 59 < exc.retry_after <= 60
else:
    raise AssertionError("expected a refusal")

keyed = KeyedRateLimiter(1, 60)
assert keyed.try_acquire("a") and keyed.try_acquire("b") and not keyed.try_acquire("a")

async def main() -> None:
    async with RateLimiter(3, 1):
        pass

asyncio.run(main())
print("consumer ok", taplimit.__version__)
"""


def _sh(*cmd: str, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False, cwd=cwd)
    assert result.returncode == 0, f"{cmd}\n{result.stdout}\n{result.stderr}"
    return result


@pytest.fixture(scope="module")
def installed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("e2e")
    dist = base / "dist"
    _sh(sys.executable, "-m", "pip", "wheel", "--no-deps", "-q", "-w", str(dist), str(ROOT))
    wheels = list(dist.glob("taplimit-*.whl"))
    assert len(wheels) == 1
    env_dir = base / "venv"
    venv.EnvBuilder(with_pip=True).create(env_dir)
    bindir = env_dir / ("Scripts" if os.name == "nt" else "bin")
    python = bindir / ("python.exe" if os.name == "nt" else "python")
    _sh(str(python), "-m", "pip", "install", "-q", "--no-index", str(wheels[0]))
    return bindir


def _python(bindir: Path) -> str:
    return str(bindir / ("python.exe" if os.name == "nt" else "python"))


def test_the_installed_wheel_works_for_a_consumer(installed: Path, tmp_path: Path) -> None:
    script = tmp_path / "consumer.py"
    script.write_text(CONSUMER, encoding="utf-8")
    result = _sh(_python(installed), str(script), cwd=str(tmp_path))
    assert "consumer ok" in result.stdout


def test_the_installed_wheel_ships_type_information(installed: Path) -> None:
    code = (
        "import importlib.resources as r; print(r.files('taplimit').joinpath('py.typed').is_file())"
    )
    assert _sh(_python(installed), "-c", code).stdout.strip() == "True"


def test_the_installed_console_script_throttles_lines(installed: Path, tmp_path: Path) -> None:
    exe = installed / ("taplimit.exe" if os.name == "nt" else "taplimit")
    source = tmp_path / "lines.txt"
    source.write_bytes(b"one\ntwo\nthree\nfour\n")
    result = subprocess.run(
        [str(exe), "2/0.5s", str(source)], capture_output=True, timeout=60, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [b"one", b"two", b"three", b"four"]
    dropped = subprocess.run(
        [str(exe), "--drop", "1/h"], input=b"a\nb\n", capture_output=True, timeout=60, check=False
    )
    assert dropped.stdout.splitlines() == [b"a"]
    assert b"dropped 1 line(s)" in dropped.stderr
