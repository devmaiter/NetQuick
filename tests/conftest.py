# -*- coding: utf-8 -*-
"""Shared test setup."""
import logging

import pytest


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
