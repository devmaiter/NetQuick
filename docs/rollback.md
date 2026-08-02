# Release rollback

Knight Capital went under in 45 minutes partly because their rollback had never
been rehearsed. NetQuick's rollback is deliberately boring: every install path
(desktop shortcut, `netquick` on the PATH, the start-with-Windows task) points
at the same file — `%LOCALAPPDATA%\NetQuick\NetQuick.exe` — so **rolling back is
replacing that one file with a previous release's exe**. Nothing else changes.

## Procedure

1. Quit the running instance (right-click the tray icon → Quit).
2. Reinstall pinning the previous tag (`install.ps1` reads `NETQUICK_TAG`;
   without it, it installs the latest release):

   ```powershell
   $env:NETQUICK_TAG = "v1.2.2-beta"   # the tag to go back to
   irm https://raw.githubusercontent.com/devmaiter/NetQuick/main/install.ps1 | iex
   ```

3. The installer verifies the download's SHA256 against the hash published in
   the release notes (releases since v1.2.2-beta publish it; for older ones,
   compare `Get-FileHash` manually). On mismatch it deletes the download and
   aborts — a rollback you can't trust is not a rollback.
4. Start NetQuick again (shortcut or `netquick`). The startup task, if enabled,
   already points at the replaced exe.

To return to the current version: same procedure without `NETQUICK_TAG` (or
`Remove-Item env:NETQUICK_TAG` first).

## Rehearsal record

- **2026-08-02** — sandboxed rehearsal of the tag-pinned download path:
  `v1.2.2-beta` (19.1 MB) downloaded via the `releases/tags/<tag>` API and its
  SHA256 matched the published `4fa056e4…27e5`; the no-published-hash case was
  exercised with `v1.2.1` (18.1 MB — that release predates hash publishing, so
  its hash was recorded manually: `33d6e026…15f0`). The file-replacement step
  is exercised by every normal install, so the full path is covered.

Re-rehearse after any change to `install.ps1` or `release.yml`.
