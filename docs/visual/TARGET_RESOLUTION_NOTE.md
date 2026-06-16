# Pedro Dashboard — target resolution note (2026-06-16)

The Oracle skin plan (`hermes_oracle_dashboard_skin_plan_md/`) was authored
targeting 1920x1080. The actual iMac-Hermes kiosk host panel is **1920x1200
native (16:10)**, confirmed by `DISPLAY=:0 xrandr --current`:

```
Screen 0: current 1920 x 1200
LVDS connected 1920x1200+0+0
1920x1200     60.24*+
1920x1080     60.00
```

Per Jurand's mid-turn instruction "to musi byc 1920x1200" the Pedro Dashboard
implements and screenshots Oracle at 1920x1200, NOT 1920x1080.

## Consequences

- Layout grid (`.layout` columns `432px 1fr 736px`) is sized for ~1200
  vertical pixels and stays correct.
- Visual acceptance screenshots in `docs/visual/` are 1920x1200 PNGs.
- Asset hooks (`--oracle-corner-url`, `--oracle-header-url`,
  `--oracle-panel-bg-url`, `--oracle-ticker-frame-url`,
  `--oracle-video-frame-url`, `--oracle-slideshow-frame-url`) are
  pixel-resolution agnostic — they are CSS background overlays and
  adapt to the panel/card size automatically.
- When generating GPT-image-2 assets later, render them at
  panel-relative sizes, not at 1920x1080 desktop backgrounds.

## Files in the plan still mentioning 1920x1080

- `01_MASTER_BRIEF_DLA_HERMESA.md` line 85, 115
- `04_CODEX_TASKS_KROK_PO_KROKU.md` lines 21, 171, 368
- `05_GPT_IMAGE_2_ASSET_PROMPTS.md` line 122
- `08_ASSET_IMPLEMENTATION_GUIDE.md` line 188
- `10_QA_VISUAL_ACCEPTANCE.md` line 5
- `11_RISK_RULES_POLSAT_GOOGLE_ASSETS.md` line 122
- `12_COPY_PASTE_PROMPT_DLA_HERMESA.md` line 78

These references can stay; they are plan artifacts on a separate path
under `~/linus1/pedro/...` and Pedro is the live host-local implementation
that pins 1920x1200.
