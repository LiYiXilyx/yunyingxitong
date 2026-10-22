#!/usr/bin/env python3
"""Generate the AMD bundle with metadata from the authoritative server definitions."""
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
subprocess.run(['node',str(ROOT/'scripts/build-plugin-client.mjs')],cwd=ROOT,check=True)
