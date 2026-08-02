# -*- coding: utf-8 -*-
"""
Error-budget report from NetQuick's structured log (issue #24, SRE lesson:
budget the failure instead of denying it — turn "how reliable is it?" into
arithmetic).

Every attempt of set_static/set_dhcp/revert writes one line with
op/result/reason/dur_ms. This script turns that raw material into numbers:
success rate per operation against a reference target, most frequent failure
reasons and duration percentiles.

Usage:  python report.py            (reads %LOCALAPPDATA%\\NetQuick\\netquick.log)
        python report.py PATH       (any log file, e.g. one from another machine)

Exit code 1 if the overall success rate is below the target — usable in CI or
a scheduled check.

SLO accounting (same contract as netops._log_op): 'reject' is validation or
user input — outside the budget; 'ok' counts as success; 'partial' and
'error' count as failure inside the budget.
"""
import re
import sys

TARGET = 99.0  # % of successful operations among the SLO-relevant ones

# 'key=value' pairs where the value may contain spaces (reason=gateway outside
# the subnet dur_ms=12): the value runs until the next ' key=' or end of line.
_PAIR = re.compile(r"(\w+)=((?:(?!\s\w+=).)*)")


def parse_log(lines):
    """The op= lines of the log as a list of dicts (other lines are noise:
    cmd warnings, tracebacks). Malformed lines are skipped, never fatal."""
    entries = []
    for line in lines:
        if "op=" not in line or "result=" not in line:
            continue
        entry = {k: v.strip() for k, v in _PAIR.findall(line)}
        if entry.get("op") and entry.get("result"):
            entries.append(entry)
    return entries


def summarize(entries):
    """Per-op aggregates: attempts, results, success rate over the SLO subset,
    top failure reasons and duration percentiles."""
    ops = {}
    for e in entries:
        s = ops.setdefault(e["op"], {"attempts": 0, "ok": 0, "partial": 0,
                                     "error": 0, "reject": 0, "other": 0,
                                     "reasons": {}, "durs": []})
        s["attempts"] += 1
        result = e["result"] if e["result"] in ("ok", "partial", "error",
                                                "reject") else "other"
        s[result] += 1
        if result in ("partial", "error", "reject") and e.get("reason"):
            s["reasons"][e["reason"]] = s["reasons"].get(e["reason"], 0) + 1
        try:
            s["durs"].append(int(e.get("dur_ms", "")))
        except ValueError:
            pass
    return ops


def _percentile(sorted_values, pct):
    if not sorted_values:
        return 0
    index = min(len(sorted_values) - 1,
                round(pct / 100 * (len(sorted_values) - 1)))
    return sorted_values[index]


def _rate(s):
    """Success % over the SLO subset (ok vs partial+error), or None if the op
    has only rejects (nothing inside the budget to measure)."""
    slo_total = s["ok"] + s["partial"] + s["error"]
    return None if slo_total == 0 else 100 * s["ok"] / slo_total


def format_report(ops, source, target=TARGET):
    lines = [f"NetQuick error budget - {source}",
             f"Target: >={target}% success "
             "(ok vs partial+error; rejects are outside the budget)", ""]
    if not ops:
        lines.append("No operations in the log yet: nothing to measure.")
        return "\n".join(lines), True
    total_ok = total_slo = 0
    for op in sorted(ops):
        s = ops[op]
        rate = _rate(s)
        total_ok += s["ok"]
        total_slo += s["ok"] + s["partial"] + s["error"]
        head = (f"{op:<12} attempts={s['attempts']:<4} ok={s['ok']:<4} "
                f"partial={s['partial']:<3} error={s['error']:<3} "
                f"rejects={s['reject']:<3}")
        if rate is None:
            lines.append(f"{head} success=—      (only rejects)")
        else:
            verdict = "ok" if rate >= target else "BREACH"
            lines.append(f"{head} success={rate:5.1f}%  [{verdict}]")
        for reason, count in sorted(s["reasons"].items(),
                                    key=lambda kv: -kv[1])[:3]:
            lines.append(f"{'':<13}reason x{count}: {reason}")
        durs = sorted(s["durs"])
        if durs:
            lines.append(f"{'':<13}dur_ms p50={_percentile(durs, 50)} "
                         f"p95={_percentile(durs, 95)} max={durs[-1]}")
    lines.append("")
    if total_slo == 0:
        lines.append("OVERALL: only rejects so far — budget untouched.")
        return "\n".join(lines), True
    overall = 100 * total_ok / total_slo
    within = overall >= target
    lines.append(f"OVERALL: {overall:.1f}% vs {target}% target -> "
                 + ("WITHIN BUDGET" if within else "BUDGET BREACHED"))
    return "\n".join(lines), within


def main(argv):
    if len(argv) > 1:
        path = argv[1]
    else:
        import netops
        path = netops.LOG_FILE
    try:
        with open(path, encoding="utf-8") as f:
            entries = parse_log(f)
    except OSError as e:
        print(f"Could not read {path}: {e}")
        return 2
    text, within = format_report(summarize(entries), path)
    print(text)
    return 0 if within else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
