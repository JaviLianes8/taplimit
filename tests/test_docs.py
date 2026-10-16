"""Every example in the docstrings, the README and the guide runs and shows what it says."""

from __future__ import annotations

import doctest
import importlib
import pkgutil
import re
from pathlib import Path

import pytest

import taplimit

ROOT = Path(__file__).resolve().parent.parent
MODULES = ["taplimit"] + [f"taplimit.{m.name}" for m in pkgutil.iter_modules(taplimit.__path__)]


@pytest.mark.parametrize("name", MODULES)
def test_module_doctests_pass(name: str) -> None:
    module = importlib.import_module(name)
    result = doctest.testmod(module, optionflags=doctest.ELLIPSIS)
    assert result.failed == 0


@pytest.mark.parametrize("name", taplimit.__all__)
def test_every_public_name_runs_its_own_example(name: str) -> None:
    tests = doctest.DocTestFinder(recurse=False).find(getattr(taplimit, name), name)
    assert sum(len(t.examples) for t in tests) >= 3
    runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS)
    for test in tests:
        test.globs = {name: getattr(taplimit, name)}
        runner.run(test)
    assert runner.summarize(verbose=False).failed == 0


def _blocks(name: str) -> list[str]:
    text = (ROOT / name).read_text("utf-8")
    return re.findall(r"```python\n(.*?)```", text, flags=re.S)


@pytest.mark.parametrize("name", ["README.md", "GUIDE.md"])
def test_python_examples_run(name: str, capsys: pytest.CaptureFixture[str]) -> None:
    blocks = _blocks(name)
    assert len(blocks) >= 3
    namespace: dict[str, object] = {"__name__": "__docs__"}
    for block in blocks:
        exec(compile(block, name, "exec"), namespace)
    out = capsys.readouterr().out
    if name == "README.md":
        assert "88 0.0" in out
    else:
        assert "[0, 1, 2, 3, 4, 5]" in out


def test_the_readme_links_are_absolute() -> None:
    text = (ROOT / "README.md").read_text("utf-8")
    links = re.findall(r"\]\(([^)]+)\)", text)
    assert links and all(link.startswith("https://") for link in links)


def test_no_doc_uses_an_em_dash_or_names_a_missing_file() -> None:
    for name in ["README.md", "GUIDE.md", "CHANGELOG.md", "CONTRIBUTING.md"]:
        text = (ROOT / name).read_text("utf-8")
        assert "—" not in text, name
    for path in ["GUIDE.md", "CHANGELOG.md", "LICENSE"]:
        assert (ROOT / path).is_file()
