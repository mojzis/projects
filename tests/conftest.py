"""Shared pytest fixtures."""

import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_from_outer_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop inherited GIT_* variables.

    When pytest runs from a git hook, GIT_DIR/GIT_INDEX_FILE point at the outer
    repository, so tests that drive real git in a tmp repo would operate on (and
    reconfigure) the repo being committed to instead.
    """
    for name in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(name)
