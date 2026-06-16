#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import os
import subprocess
import time
from pathlib import Path

ROOT = Path('/home/imac-hermes/projects/pedro_dashboard')
LOCK = Path('/tmp/pedro-kiosk-brightness-loop.lock')
LOG = ROOT / 'app/logs/kiosk-brightness.log'
INTERVAL = int(os.environ.get('PEDRO_BRIGHTNESS_INTERVAL', '300'))

os.environ.setdefault('DISPLAY', ':0')
os.environ.setdefault('XAUTHORITY', str(Path.home() / '.Xauthority'))
LOG.parent.mkdir(parents=True, exist_ok=True)

with LOCK.open('w') as lock_file:
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('kiosk brightness loop already running')
        raise SystemExit(0)

    while True:
        proc = subprocess.run(
            [str(ROOT / 'scripts/set-kiosk-brightness.sh')],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=30,
            env=os.environ.copy(),
        )
        with LOG.open('a', encoding='utf-8') as f:
            ts = time.strftime('%Y-%m-%dT%H:%M:%S%z')
            if proc.stdout:
                for line in proc.stdout.splitlines():
                    f.write(f'{ts} {line}\n')
            if proc.stderr:
                for line in proc.stderr.splitlines():
                    f.write(f'{ts} STDERR {line}\n')
            if proc.returncode:
                f.write(f'{ts} EXIT {proc.returncode}\n')
        time.sleep(INTERVAL)
