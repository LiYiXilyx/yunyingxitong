# 社区插件来源守门

当前政策固定 NocoBase 2.2.30，镜像摘要见[政策文件](../deploy/community-policy.json)。2026-10-22以官方GitHub `v2.2.30` 标签ref及完整源码归档交叉核对：commit为 `d7bbafe86257cc3ccd33dd03930e09468b96d7c1`。此前npm元数据中的gitHead不是有效的40位提交，被舍弃。政策保存官方源地址、归档SHA256、逐插件源路径及package.json SHA256；修改版本须重新从官方固定commit审核生成政策，不能只把新包名手工加入白名单。

官方公开源码包含110个 `@nocobase/plugin-*` 包；此次镜像包含100个，名称与版本均能在该源码找到。守门不是仅凭镜像标签自认免费，而是将实际安装清单与固定官方公开社区源码包元数据比较。自研 `@project2/plugin-ops` 单独允许版本0.1.0，不冒称官方社区源码。

## 执行

默认入口先用Compose定位唯一nocobase容器，仅格式化读取 `Config.Image`，要求实际引用严格等于政策中的镜像名加 `@` 摘要；tag-only、摘要变化或查询失败都返回非0，不读取完整inspect及环境变量。随后从当前postgres的 `applicationPlugins` 权威表查询 packageName、version、installed、enabled，并与当前nocobase容器中的插件文件交叉核对。通过容器本地socket读取，不读取options、授权键或秘密文件。查询失败、表为空、安装/启用包缺文件或版本不符均失败。

```sh
make verify-community
python3 -m unittest discover -s tests
```

也支持显式启用数组供离线核验或排障：`scripts/verify-community.sh .local/intake/enabled-plugins.json`。该模式只核对传入启用清单，不等价于默认数据库完整安装状态核验，不能用于替代部署验收。

入口通过项目Compose包装器从正在运行的nocobase读取所有命名空间下 `plugin-*` 的实际package元数据，以及根node_modules中的 `plugin-*`。不读取或输出秘密文件内容，不开启试用，不连接旺店通。离线核验器也可用于明确标记的安装清单：

```sh
python3 scripts/community_guard.py --installed-json /tmp/installed.json --enabled-json /tmp/enabled.json
```

缺运行时启用清单、空安装清单、重复安装名、未知/商业/试用包、版本或license元数据改变，以及启用插件未出现在已核验安装清单时，均返回非0。新增其他目录或不以plugin-命名的插件，必须同步扩展安装发现方法；启用清单仍会拒绝没有实际安装核验证据的包。政策不允许通过“停用试用”来将商业包视作免费。

## 许可证与残余检查

97个镜像插件的package license直接与源码元数据比较。`plugin-ai`、`plugin-block-comment`、`plugin-idp-oauth` 在镜像和公开源码package均未声明license，政策明确标记使用仓库根package.json的Apache-2.0元数据作为来源证据，保留根package摘要。官方源码存在历史AGPL/双许可文件头，这里不宣称逐文件、全部传递依赖或法律许可审计完成。公网可读本身也不等于所有外部服务免费。

本守门核验名称、固定版本及许可证元数据，不对编译产物逐字节重建，也无法检测同版本包代码被替换。镜像摘要固定是另一层完整性前提；项目插件源代码应由版本控制审查。部署后仍需从数据库核实完整安装/启用状态及插件管理页面不存在试用授权；默认数据库查询使用已核实的applicationPlugins表，不猜测其他版本表结构。首期不配置AI外部服务等额外能力。

## 已执行验证

先写9项守门测试，缺生产脚本时全部预期失败；实现后通过。新增缺license显式来源回退用例，先失败再通过。新增运行时数据库版本漂移、停用但已安装未知插件、空表用例，观察失败后实现。本文件守门测试有14个独立测试方法；继承导致32次执行，并非32个独立用例。全项目 `python3 -m unittest discover -s tests` 当前36次执行通过（含继承重复执行及其他模块测试）。真实已下载镜像100包与官方源政策比较，缺启用清单返回非0，未将离线bundle核对冒充运行时验收。

本次默认 `make verify-community` 实测通过：实际安装101包（含自研插件），数据库启用77包；此结果对应执行时状态，后续改变须重跑。

实际容器镜像引用检查同样先加入失败测试，再实现精确引用校验；默认make verify-community在镜像校验接入后已再次通过。
