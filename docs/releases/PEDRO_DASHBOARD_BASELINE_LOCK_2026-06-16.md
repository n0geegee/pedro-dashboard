# Pedro Dashboard baseline lock — 2026-06-16

Status: source-of-truth marker for the next MiniMax fork. There is no GitHub repository for this project.

## Current preserved baseline

- Project root: `/home/imac-hermes/projects/pedro_dashboard`
- Accepted version: `VERSION = 1.1`
- Release note: `docs/releases/PEDRO_DASHBOARD_V1.1.md`
- Integration/status lock: `PEDRO_INTEGRATION_STATUS.md`
- Current post-v1.1 skin preview note: `docs/SPRING_WINAMP_MAGIC_SKIN_PREVIEW_2026-06-15.md`

## Backup before MiniMax/oracle work

- Snapshot: `/home/imac-hermes/projects/pedro_dashboard_backups/pedro-dashboard-v1.1-current-before-minimax-oracle-20260616-004920.tgz`
- SHA256: `775549435c373108c4fc85438398ca77a4c481d5e7fbecc0ce75782efa995c16`

## Fork rule

Future MiniMax/oracle work should fork/copy from `/home/imac-hermes/projects/pedro_dashboard`, not from `/mnt/linus1/hermes/projects/pedro_dashboard`.

`/mnt/linus1/pedro/hermes_oracle_dashboard_skin_plan_md.zip` contains the new instruction pack, but the active code baseline remains the host-local project root above.

## Preserve while changing

- Passive kiosk behavior: no buttons/links/click handlers.
- v1.1 readability rules: Kamila calendar max 3 visible entries; volleyball chronological mixed list; Polsat legal browser overlay inside UR card; no XFCE panel overlay.
- Live state contract: `app/state/*.json`; connectors write atomic JSON; no raw private logs/prompts/tokens in state.
