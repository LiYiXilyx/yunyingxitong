#!/usr/bin/env python3
"""Fail-closed plugin metadata guard; not a full dependency license audit."""
import argparse
import json
import re
import sys
from pathlib import Path


def validate(policy, installed, enabled):
    errors = []
    if not re.fullmatch(r'[0-9a-f]{40}', policy.get('source_commit', '')):
        errors.append('官方源码commit缺失或无效')
    if not isinstance(installed, list) or not installed:
        return errors + ['实际安装插件清单缺失或为空']
    official = policy.get('official_plugins', {})
    project = policy.get('project_plugins', {})
    seen = set()
    for item in installed:
        if not isinstance(item, dict) or not isinstance(item.get('name'), str):
            errors.append('安装插件清单格式错误')
            continue
        name = item['name']
        if name in seen:
            errors.append(f'重复安装插件: {name}')
        seen.add(name)
        expected = official.get(name) or project.get(name)
        if not expected:
            errors.append(f'非公开社区或未批准插件: {name}')
            continue
        if item.get('version') != expected.get('version'):
            errors.append(f'插件版本变化: {name}')
        if name in official:
            if not expected.get('source_path', '').startswith('packages/plugins/@nocobase/'):
                errors.append(f'缺少官方社区源码路径: {name}')
            fallback = (expected.get('license') is None and item.get('license') is None
                        and expected.get('license_fallback') == 'repository-root-package-json'
                        and policy.get('repository_license') == 'Apache-2.0')
            if not fallback and (not expected.get('license') or item.get('license') != expected['license']):
                errors.append(f'插件许可证元数据不匹配: {name}')
    if not isinstance(enabled, list):
        errors.append('缺少权威运行时启用插件清单；仅镜像核验不能通过')
    else:
        for name in enabled:
            if not isinstance(name, str) or name not in seen:
                errors.append(f'启用插件不在已核验安装清单: {name}')
    return errors


def validate_runtime(installed, rows):
    if not isinstance(rows, list) or not rows:
        return ['运行时插件表为空或查询不完整']
    by_name = {p['name']: p for p in installed}
    errors = []
    for row in rows:
        if not isinstance(row, dict):
            errors.append('运行时插件行格式错误')
            continue
        if not (row.get('enabled') or row.get('installed')):
            continue
        name = row.get('packageName')
        package = by_name.get(name)
        if not package or row.get('version') != package.get('version'):
            errors.append(f'数据库安装/启用插件与文件版本不符: {name}')
    return errors


def validate_image(policy, actual_image):
    expected = policy.get('image', '') + '@' + policy.get('image_digest', '')
    return [] if actual_image and actual_image == expected else ['实际容器镜像引用与固定摘要政策不符']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', type=Path, default=Path('deploy/community-policy.json'))
    parser.add_argument('--installed-json', type=Path, required=True)
    parser.add_argument('--enabled-json', type=Path)
    parser.add_argument('--runtime-json', type=Path)
    parser.add_argument('--actual-image')
    args = parser.parse_args()
    try:
        policy = json.loads(args.policy.read_text())
        installed = json.loads(args.installed_json.read_text())
        enabled = json.loads(args.enabled_json.read_text()) if args.enabled_json else None
        runtime = json.loads(args.runtime_json.read_text()) if args.runtime_json else None
        if runtime is not None:
            enabled = [r.get('packageName') for r in runtime if isinstance(r, dict) and r.get('enabled')]
        errors = validate(policy, installed, enabled)
        if runtime is not None:
            errors += validate_runtime(installed, runtime)
            errors += validate_image(policy, args.actual_image)
    except (ValueError, OSError, TypeError, AttributeError) as exc:
        print(f'社区核验失败: {type(exc).__name__}', file=sys.stderr)
        return 1
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(f'社区来源/版本/元数据门禁通过：安装{len(installed)}个，启用{len(enabled)}个；不代表完整依赖许可审计')
    return 0


if __name__ == '__main__':
    sys.exit(main())
