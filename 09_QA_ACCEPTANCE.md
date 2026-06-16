# 09 — QA acceptance checklist

## Layout / UI

- [ ] Dashboard opens at `http://127.0.0.1:17890/`.
- [ ] 1920×1200 has no page scroll.
- [ ] Header shows time, sync freshness, privacy mode.
- [ ] UL, UR, LL, LR are visible simultaneously.
- [ ] LL clearly reads as Pedro Voice Console.
- [ ] Text is readable from across the room.
- [ ] Missing widget state does not white-screen the UI.
- [ ] Corrupt widget JSON produces degraded card only.

## Pedro Voice Console

- [ ] `voice_console.json` state `idle` renders correctly.
- [ ] `listening_for_wake` renders with wake phrase `hej Pedro`.
- [ ] `wake_detected` has visible feedback.
- [ ] `recording`, `transcribing`, `thinking`, `searching` are distinct.
- [ ] `speaking_or_result` shows a large result.
- [ ] `needs_clarification` shows a short question.
- [ ] `error` shows a public-safe message.
- [ ] `privacy_blocked` hides sensitive content.

## Privacy

- [ ] `normal` still hides secrets/raw logs/tokens.
- [ ] `private` hides full transcript and personal result details.
- [ ] `guest` hides transcript, result details, project/client names and private alerts.
- [ ] Backend/state writers redact before frontend receives data.
- [ ] No raw Discord messages appear.
- [ ] No `.env`, token, API key, or secret path appears.

## MX Linux / no-systemd ops

- [ ] No MVP script requires `systemctl`.
- [ ] No MVP script requires systemd timer.
- [ ] No MVP runbook requires `journalctl`.
- [ ] XDG autostart files install under `~/.config/autostart/`.
- [ ] Crontab fallback is shown before modification.
- [ ] File logs are written under `~/.local/state/pedro_dashboard/logs/`.

## Watchdog / durability

- [ ] `scripts/start-dashboard.sh` starts server.
- [ ] `scripts/stop-dashboard.sh` stops server.
- [ ] `scripts/status-dashboard.sh` reports process/port/health.
- [ ] `scripts/start-kiosk.sh` opens Chrome kiosk.
- [ ] `scripts/watchdog-dashboard.sh --once` detects and repairs stopped server.
- [ ] Killing Chrome triggers kiosk restore.
- [ ] Killing server triggers server restore.
- [ ] Reboot/login brings dashboard back.

## Health probes

- [ ] RAM/swap/disk/uptime are real and timeout-safe.
- [ ] Hermes gateway status is public-safe.
- [ ] OpenViking status is public-safe.
- [ ] Offline Hermes/OpenViking shows degraded state, not UI crash.
- [ ] Internet outage shows stale/degraded state.

## Resource budget

- [ ] No Node/Electron/React watcher in MVP.
- [ ] Dashboard and Chrome run for 1 hour without runaway RAM/swap.
- [ ] Probe scripts use short timeouts.
- [ ] Routine refreshes are deterministic/no-agent.

## Final MVP acceptance

- [ ] Jurand can glance at screen and understand: status, focus, alerts, Pedro state.
- [ ] Dashboard is safe to leave visible in the room under selected privacy mode.
- [ ] The project can now proceed to Phase B voice design without rebuilding UI.
