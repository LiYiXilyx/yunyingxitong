# T02 版本与费用边界

核验日期：2026-10-22。本地开发环境；尚未连接真实店铺。镜像摘要已在 `deploy/compose.yaml` / `deploy/Dockerfile.ops-data` 固定，禁止替换为 latest。

| 组件 | 本次实际版本 | 固定方式 / 许可说明 |
|---|---|---|
| NocoBase | 2.2.30，镜像内 Node 22.23.4 | 官方稳定镜像 + SHA256；公开社区插件来源核验见下文 |
| PostgreSQL | 16.15，Debian bookworm | 16-bookworm 镜像 + SHA256；PostgreSQL License |
| 数据服务 Python | 容器 3.13.17；本机测试 3.13.2 | 3.13-slim-bookworm + SHA256；PSF |
| TypeScript 契约测试 Node | 本机 26.0.0 | `.node-version`，无需装进生产 Python 服务；Node MIT 与其依赖许可 |
| FastAPI / Uvicorn | 0.159.1 / 0.54.0 | `services/ops-data/requirements.lock`；MIT / BSD-3-Clause |
| psycopg / jsonschema | 3.3.6 / 4.26.0 | 同一完整依赖锁；LGPL-3.0 / MIT |
| AJV / ajv-formats | 8.20.0 / 3.0.1 | `contracts/package-lock.json` 固定版本及 integrity；MIT |
| 本机容器工具 | Colima 0.10.3、Docker CLI 29.9.2、Compose 5.6.1 | Homebrew 安装；Colima MIT，Docker CLI/Compose Apache-2.0；没有安装 Docker Desktop |
| 自研插件 | @project2/plugin-ops 0.1.0 | 仓库代码；私有项目 UNLICENSED 只表示尚未授予对外分发许可，不是商业插件收费 |

## 固定镜像

- NocoBase：`nocobase/nocobase:2.2.30@sha256:05b1d0244a0d0b44f5dd0f60a9ec307132232de279563406b481479593f86ba0`
- PostgreSQL：`postgres:16-bookworm@sha256:d81f7b51697014367236d07ec58b54153fc28f828b72bf247fe5c7487520bcb0`
- Python：`python:3.13-slim-bookworm@sha256:a881a81282cca8c57f97014867fa651def1b3799030cc6b1cff45ed55ba8ef36`
- 本地数据服务：`project2/ops-data:0.1.0` 由上述基础镜像、固定 Python 依赖和本仓库构建。尚未发布到镜像仓库，部署远程服务器前应发布并记录构建镜像摘要。

## 免费边界

本轮未购买商业插件、未申请或启用商业试用。守门将容器插件与官方公开社区源码和数据库实际安装/启用状态交叉核对。NocoBase 官方 v2.2.30 标签对应 commit `d7bbafe86257cc3ccd33dd03930e09468b96d7c1`；npm元数据中的不完整 gitHead 未作为证据。

公开仓库 package 主要声明 Apache-2.0，部分源码仍有历史 AGPL/商业双许可文件头；本清单和门禁不是逐文件或全传递依赖法律审计。详见[社区来源政策](community-policy.md)。旺店通、Ego、服务器与模型调用费用仍独立计算；本轮未配置模型或发送其请求。

审批、任务流转审计、动态店铺权限、可靠派单、效果复查由后续自研插件/数据服务实现，不购买同类商业插件。不把社区版页面配置误认为这些业务能力已经实现。

## 官方证据

- [NocoBase v2.2.30 发布](https://github.com/nocobase/nocobase/releases/tag/v2.2.30)
- [固定源码版本](https://github.com/nocobase/nocobase/tree/d7bbafe86257cc3ccd33dd03930e09468b96d7c1)
- [官方 Docker 安装说明](https://docs.nocobase.com/get-started/installation/docker)
- [FastAPI PyPI 元数据](https://pypi.org/pypi/fastapi/0.159.1/json)、[psycopg 元数据](https://pypi.org/pypi/psycopg/3.3.6/json)
- [AJV 官方包元数据](https://registry.npmjs.org/ajv/8.20.0)

升级流程：先在独立测试环境更新版本及锁文件，重新生成社区来源证据，运行契约/隔离/插件/重启验证，再迁移真实部署。只改白名单或标签不能算升级完成。
