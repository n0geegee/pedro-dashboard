# Pedro Spring Winamp Magic skin preview — 2026-06-15

Status: live manual preview via `scripts/set-skin.py spring`.

Intent: replace simple seasonal color overlay with a real Winamp-like skinnable UI treatment: dark metal/glass card chrome, LED/firefly dots, edge vines, corner caps, mint/gold highlights, while preserving Pedro v1.1 layout and real data.

Touched files:
- `app/static/styles.css`
- `app/static/skins/pedro_spring_winamp_ambient.svg`
- `app/static/skins/pedro_spring_winamp_edge_chrome.svg`

Backup:
- `backups/skin-work-20260615-231942/styles.css.before_winamp_magic`
- `backups/skin-work-20260615-231942/skins.before_winamp_magic/`

Verification:
- Screenshot: `/tmp/pedro_spring_winamp_magic_real_01.png`
- Polsat Chrome overlay remained real and above dashboard.
- Polsat geometry verified: `x=1183 y=92 w=706 h=488`.
- Current mode after preview: `skin=spring`, `mode=manual`.

Rollback:
```bash
cd /home/imac-hermes/projects/pedro_dashboard
scripts/set-skin.py auto
```

Design note:
This is now a real skin direction, not just green background. Next iteration can push stronger Winamp material/chrome, but must keep text/card interiors readable and avoid touching Polsat/video content.
