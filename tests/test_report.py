# -*- coding: utf-8 -*-
"""Tests of the error-budget report (issue #24) against a synthetic log."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import report

SYNTHETIC = """\
2026-07-23 01:00:00,001 INFO op=set_static result=ok reason= dur_ms=210 iface=E ip=10.0.0.5
2026-07-23 01:00:01,002 INFO cmd ['netsh'] -> 1: noise line without op
2026-07-23 01:00:02,003 INFO op=set_static result=reject reason=Invalid IP: banana dur_ms=1 iface=E
2026-07-23 01:00:03,004 INFO op=set_static result=partial reason=DNS could not be applied dur_ms=900
2026-07-23 01:00:04,005 INFO op=set_static result=error reason=netsh_fail dur_ms=1200 iface=E
2026-07-23 01:00:05,006 INFO op=set_static result=ok reason= dur_ms=300 iface=E ip=10.0.0.8
2026-07-23 01:00:06,007 INFO op=set_dhcp result=ok reason= dur_ms=150 iface=E
malformed line op= with nothing useful
2026-07-23 01:00:07,008 INFO op=revert result=ok reason=via_dhcp dur_ms=180 iface=E
"""


def _entries():
    return report.parse_log(SYNTHETIC.splitlines())


def test_parse_skips_noise_and_keeps_fields_with_spaces():
    entries = _entries()
    assert len(entries) == 7
    partial = next(e for e in entries if e["result"] == "partial")
    # reason with spaces must survive whole, not just its first word
    assert partial["reason"] == "DNS could not be applied"
    assert partial["dur_ms"] == "900"


def test_summarize_counts_and_rate():
    ops = report.summarize(_entries())
    s = ops["set_static"]
    assert (s["attempts"], s["ok"], s["partial"], s["error"], s["reject"]) \
        == (5, 2, 1, 1, 1)
    # SLO subset: 2 ok of 4 (the reject is outside the budget)
    assert report._rate(s) == 50.0
    assert report._rate(ops["set_dhcp"]) == 100.0


def test_format_shows_rate_reasons_durations_and_verdict():
    text, within = report.format_report(report.summarize(_entries()),
                                        "synthetic")
    assert not within                          # 4/6 = 66.7% < 99%
    assert "success= 50.0%" in text and "[BREACH]" in text
    assert "DNS could not be applied" in text
    assert "p50=" in text and "max=1200" in text
    assert "BUDGET BREACHED" in text


def test_only_rejects_leaves_budget_untouched():
    entries = report.parse_log([
        "2026-07-23 01:00:00,001 INFO op=set_static result=reject "
        "reason=Invalid IP dur_ms=1 iface=E"])
    text, within = report.format_report(report.summarize(entries), "synthetic")
    assert within
    assert "only rejects" in text


def test_empty_log_is_not_a_breach():
    text, within = report.format_report({}, "synthetic")
    assert within and "nothing to measure" in text


def test_main_reads_a_file_and_returns_exit_code(tmp_path, capsys):
    good = tmp_path / "good.log"
    good.write_text("2026-07-23 01:00:00,001 INFO op=set_dhcp result=ok "
                    "reason= dur_ms=100 iface=E\n", encoding="utf-8")
    assert report.main(["report.py", str(good)]) == 0
    assert "WITHIN BUDGET" in capsys.readouterr().out

    bad = tmp_path / "bad.log"
    bad.write_text("2026-07-23 01:00:00,001 INFO op=set_dhcp result=error "
                   "reason=netsh_fail dur_ms=100 iface=E\n", encoding="utf-8")
    assert report.main(["report.py", str(bad)]) == 1
    assert report.main(["report.py", str(tmp_path / "missing.log")]) == 2
