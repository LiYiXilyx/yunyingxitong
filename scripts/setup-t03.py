#!/usr/bin/env python3
"""Prepare synthetic T03 data and the four managed pages without exposing secrets."""
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CONTAINER_ACCOUNTS = '/tmp/t03-accounts.json'
SERVICES = '/app/nocobase/node_modules/@project2/plugin-ops/services'
ACCOUNT_KEYS = ('supervisor', 'operatorA', 'operatorB', 'integration')


class SetupError(RuntimeError):
    pass


def validate_accounts(raw, complete=True):
    try:
        value = json.loads(raw)
        if not isinstance(value, dict) or not value or set(value) - set(ACCOUNT_KEYS):
            raise ValueError()
        if complete and set(value) != set(ACCOUNT_KEYS):
            raise ValueError()
        for account in value.values():
            if not isinstance(account, dict) or set(account) - {'email', 'password', 'id'}:
                raise ValueError()
            if not isinstance(account['email'], str) or not account['email']:
                raise ValueError()
            if not isinstance(account['password'], str) or not account['password']:
                raise ValueError()
            # A credential is persisted before user creation; a failed first setup
            # can therefore have only some accounts and no ID for the latest one.
            if complete and 'id' not in account:
                raise ValueError()
            if 'id' in account and (type(account['id']) is not int or account['id'] < 1):
                raise ValueError()
        return value
    except (ValueError, TypeError, KeyError):
        raise SetupError('T03账号文件不完整；请恢复原凭据记录，不能自动重置密码。') from None


def setup(root=ROOT):
    root = Path(root)
    for directory in (root / '.local', root / '.local/secrets'):
        if directory.is_symlink():
            raise SetupError('拒绝使用符号链接作为本机私密目录。')
        directory.mkdir(exist_ok=True, mode=0o700)
        directory.chmod(0o700)
    secret = root / '.local/secrets/t03-accounts.json'
    original = None
    original_accounts = {}
    if secret.is_symlink():
        raise SetupError('拒绝使用符号链接作为T03账号文件。')
    if secret.exists():
        if not stat.S_ISREG(secret.stat().st_mode):
            raise SetupError('T03账号路径必须是普通文件。')
        secret.chmod(0o600)
        original = secret.read_bytes()
        original_accounts = validate_accounts(original, complete=False)

    def run(command, label, **kwargs):
        result = subprocess.run(command, cwd=root, capture_output=True, **kwargs)
        if result.returncode:
            # Container output can contain credentials or database connection details.
            raise SetupError(f'{label}失败（退出码{result.returncode}）；已停止后续步骤，未输出私密内容。')
        return result.stdout

    compose = ['scripts/compose.sh', 'exec', '-T', 'nocobase']

    def save_container_accounts(complete):
        raw = run([*compose, 'cat', CONTAINER_ACCOUNTS], '凭据安全取回')
        accounts = validate_accounts(raw, complete=complete)
        if any(
            key not in accounts or any(accounts[key][field] != previous[field]
                                       for field in ('email', 'password'))
            for key, previous in original_accounts.items()
        ):
            raise SetupError('容器返回的账号凭据发生变化；保留原本机文件并停止，禁止静默轮换。')
        fd, temporary = tempfile.mkstemp(prefix='.t03-accounts-', dir=secret.parent)
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, secret)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    run([*compose, 'sh', '-c',
         'test ! -L "$1" && { test ! -e "$1" || { test -f "$1" && chmod 600 "$1"; }; }',
         't03-private-file', CONTAINER_ACCOUNTS], '容器凭据路径检查')
    if original is not None:
        run([*compose, 'sh', '-c',
             'umask 077; test ! -L "$1" && cat > "$1" && chmod 600 "$1"',
             't03-private-copy', CONTAINER_ACCOUNTS], '现有凭据同步', input=original)
    try:
        run([*compose, 'env', 'NODE_MODULES_PATH=/app/nocobase/node_modules',
             'node', f'{SERVICES}/bootstrap-synthetic.js', CONTAINER_ACCOUNTS], '合成数据准备')
    except SetupError as error:
        try:
            save_container_accounts(complete=False)
        except (SetupError, OSError):
            raise SetupError(f'{error} 未能取回可校验的恢复记录，已保留原本机文件。') from None
        raise SetupError(f'{error} 已私密保存账号恢复记录，可再次执行make setup-t03继续。') from None
    save_container_accounts(complete=True)
    run([*compose, 'env', 'NODE_MODULES_PATH=/app/nocobase/node_modules',
         'node', f'{SERVICES}/seed-events.js'], '合成事件引用修复')
    run(['node', 'scripts/setup-nocobase-pages.mjs'], '四个业务页面配置')
    print('T03合成数据及页面已准备。账号仅保存在.local/secrets/t03-accounts.json（0600）。')


if __name__ == '__main__':
    try:
        setup()
    except (SetupError, OSError) as error:
        # OSError text may include paths, but never include subprocess output or JSON.
        raise SystemExit(str(error)) from None
