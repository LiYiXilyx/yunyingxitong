#!/usr/bin/env python3
"""Create local-only development secrets once; never print values."""
import argparse
import os
from pathlib import Path
import secrets
import shutil


def write_once(path: Path, content: str):
    if path.is_symlink():
        raise ValueError(f'refuse symlink: {path.name}')
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if not path.is_file():
            raise ValueError(f'not a regular file: {path.name}')
        path.chmod(0o600)
        return
    with os.fdopen(fd, 'w') as handle:
        handle.write(content)


def bootstrap(root: Path):
    for directory in (root/'.local', root/'.local/secrets', root/'.local/intake'):
        if directory.is_symlink():
            raise ValueError('refuse symlink directory')
        directory.mkdir(exist_ok=True, parents=True, mode=0o700)
        directory.chmod(0o700)
    values={key:secrets.token_hex(32) for key in ('APP_KEY','POSTGRES_PASSWORD','NOCO_DB_PASSWORD','OPS_DB_PASSWORD','INIT_ROOT_PASSWORD')}
    values['INIT_ROOT_EMAIL']='owner@project2.local'
    write_once(root/'.local/secrets/deploy.env', '# Generated local development credentials. Do not commit or share.\n'+''.join(f'{key}={value}\n' for key,value in values.items()))
    write_once(root/'.local/secrets/wdt.env', '# Authorized operator fills values after confirming the WDT product/API version.\n# Never paste credentials into chat. Not used by T02.\nWDT_APP_NAME=\nWDT_SID=\nWDT_SIGNING_KEY=\nWDT_BASE_URL=\n')
    template=root/'docs/intake/two-stores.md'
    if template.exists():
        write_once(root/'.local/intake/two-stores.md',template.read_text())
    print('本地配置已准备；已有内容保留。路径：.local/secrets/deploy.env、.local/secrets/wdt.env、.local/intake/')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    try:
        bootstrap(args.root)
    except (ValueError, OSError) as exc:
        raise SystemExit(f'Bootstrap failed: {exc}')
