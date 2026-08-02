# -*- coding: utf-8 -*-
"""Shared test setup."""
import logging

import pytest

# FoundationDB lesson (issue #23): reproducibility as a superpower. The
# property-based suite always runs derandomized (fixed seed derived from the
# test), so a failure in CI reproduces identically on any machine, and
# print_blob gives the @reproduce_failure line for the minimal example.
try:
    from hypothesis import settings

    settings.register_profile("netquick", derandomize=True, print_blob=True,
                              deadline=None)
    settings.load_profile("netquick")
except ImportError:      # hypothesis not installed: the property file skips
    pass


@pytest.fixture(autouse=True, scope="session")
def _tests_do_not_write_the_real_log():
    """The 'netquick' logger writes to %LOCALAPPDATA%\\NetQuick\\netquick.log
    the moment netops is imported. Without this, every pytest run pollutes the
    USER's real log with fake rejects/errors — and since issue #24 that log is
    the source of the error-budget arithmetic, so test noise would eat the
    budget. caplog-based tests still work: they attach their own handler."""
    log = logging.getLogger("netquick")
    real_handlers = list(log.handlers)
    for h in real_handlers:
        log.removeHandler(h)
    log.addHandler(logging.NullHandler())
    yield
    for h in log.handlers[:]:
        log.removeHandler(h)
    for h in real_handlers:
        log.addHandler(h)
