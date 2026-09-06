# Pedro Dashboard v1.4.11 — accepted LR full-frame slideshow

Date: 2026-06-20
Status: ACCEPTED by Jurand on the physical iMac/Pedro kiosk.

## What changed

The LR Google Photos slideshow now fills the inner frame much more tightly.

Accepted CSS lock:

- `app/static/styles.css`
  - `.card--slideshow .card__body--slideshow { padding: 2px 3px 4px; }`
- `app/static/hermes-oracle.css`
  - oracle LR override also uses `padding: 2px 3px 4px;`
- Portrait and square photos keep the previously accepted gentle overscan:
  - portrait: `background-size: auto 106%;`
  - square: `background-size: auto 104%;`

## Acceptance screenshot

Geometry was checked using a forced true-landscape Google Photos image without letterbox, so the LR fill judgment was not biased by portrait/square side bars.

Accepted screenshot captured on the physical kiosk and locked in the project:

`docs/releases/assets/PEDRO_DASHBOARD_V1.4.11_lr_fullframe_landscape.png`

Original capture path on the iMac during QA:

`/tmp/pedro-qa/lr_fullframe_landscape.png`

A copy was delivered to Discord from Dell as:

`/tmp/pedro-lr-fullframe-landscape.png`

## Verification

- Physical iMac/Pedro kiosk restarted and rendered the updated CSS.
- Dashboard health endpoint returned OK at `http://127.0.0.1:17888/api/health`.
- Photos rotator was restored after the temporary forced-landscape QA state.
- Final geometry: slideshow fills the LR frame closely without covering the header, ticker, or oracle ornament frame.

## Rollback

Use git:

```bash
cd /home/imac-hermes/projects/pedro_dashboard
git revert v1.4.11
```

Accepted-state archive before the commit:

```text
/home/imac-hermes/projects/pedro_dashboard_backups/pedro_dashboard_v1.4.11_accepted_lr_fullframe_20260620-104030.tgz
/home/imac-hermes/projects/pedro_dashboard_backups/pedro_dashboard_v1.4.11_accepted_lr_fullframe_20260620-104030.tgz.sha256
```
