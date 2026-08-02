# Engineering review — July 2026

A one-person FMEA + STRIDE pass over NetQuick 1.2.x, done between 2026-07-22 and
2026-07-27. This document versions the findings that until now only existed as
scattered comments in code and tests (Meta's and AT&T's postmortems are useful
*because* they are written down). Finding IDs (FM-*) keep the numbering of the
original review notes, so gaps in the sequence are expected.

## Method

- **FMEA-lite**: for each operation the widget performs (apply static IP, apply
  DHCP, save profiles, scan, start with Windows), ask *how can this fail, how
  would we notice, what would the user see?*
- **STRIDE** on the Windows-integration surface (scheduled task, firewall rule,
  registry, single-instance mutex).
- Every plausible failure mode got either an experiment, a test, or an issue —
  no finding stays only as an opinion.

## Findings

| ID | Failure mode | Status | Where |
|---|---|---|---|
| FM-1 | Silent loss of saved profiles: a crash mid-write truncates `profiles.json` and the user's profiles evaporate without any message. | **Fixed** | Atomic write (temp + fsync + `os.replace`) plus a `.bak` of the last good file, with fallback on read (`store.py`, commit `53ffcde`). Regression tests in `tests/test_store.py`. |
| FM-2 | False negative in the duplicate-IP guard: a host that is powered on but silent to ping and absent from the ARP cache looks "free", so NetQuick would apply a duplicated IP. | **Mitigated** | `check_ip` forces a directed ARP probe inside the local subnet (a host that ignores ping still has to answer ARP); outside the local subnets it no longer fakes certainty and returns `unverified` → amber state (commit `34d69fc`, issue #20). Field measurement on 2026-08-02 found no ping-silent host on the available LAN (verdict H0 for that network); the silent-host scenario is covered by tests in `tests/test_netops.py`. |
| FM-3 | Partial state reported as success: the IP applies but the DNS step fails, and the widget still reported a clean green "applied" (Rogers 2022 pattern — half-configured system, happy operator). | **Fixed** | `set_static` returns `ok=False` with `result=partial` in the log when DNS was requested and failed; the UI gained a third amber state (green = clean success, amber = applied with warnings, red = not applied). Commit `cad0fca`, issue #22. |
| FM-5 | Local privilege escalation (TOCTOU) around start-with-Windows: the scheduled-task XML used to be generated in a user-writable folder, and the app auto-registered an elevated startup task on first run. | **Mitigated** | The app no longer auto-registers anything on first run; start-with-Windows is an explicit user option, off by default. When enabled, the `task.xml` is generated in `%SystemRoot%\Temp` (writable only by admins/SYSTEM) with a random name and deleted afterwards; if that folder is not writable the task is simply not created — never in an insecure spot. Commit `fc0ea06`; tests in `tests/test_winsetup.py`. |

## Invariants

- **INV-4 — durability**: a profile the user saved is never silently lost; any
  write either completes or leaves the previous file intact (see FM-1).
- **Transactional honesty**: an operation that leaves the system half-done must
  not report a clean success (see FM-3).
- **Never fake certainty**: when the guard cannot verify that an IP is free, it
  says so instead of guessing (see FM-2).

## Observability ("Phase 5")

The review found that failures were invisible: only successes left traces. Since
`53ffcde` every *attempt* of `set_static`/`set_dhcp`/`revert` writes one
structured line (`op= result= reason= dur_ms=`) to
`%LOCALAPPDATA%\NetQuick\netquick.log`, with `result` ∈ {ok, partial, reject,
error} — `reject` (validation/user) is outside the reliability target, `error`
(the OS failed) is inside it. That log is the raw material for the error-budget
report (issue #24).

## Follow-up backlog

The remaining reliability debt from this review lives as GitHub issues labeled
`P2-deuda` (#23–#26, #28, #29): property-based testing, error budget, widget
supervision, static preflight, SimOps dry-run, rehearsed rollback.
