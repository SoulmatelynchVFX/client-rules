# client-rules

用于 iOS Shadowrocket 的应用分流配置：已列出的国内应用直连，境外应用走代理，国内 IP / `.cn` 直连兜底，其余流量走代理。

## 文件

| 文件 | 说明 |
|---|---|
| `shadowrocket.conf` | Shadowrocket 原生配置，包含斗鱼直连；不含节点、订阅或 HTTPS 解密设置 |
| `rules.yaml` | 历史规则清单，保留用于对照，不是完整客户端配置 |
| `scripts/validate_rules.py` | 离线结构校验：字段、重复匹配条件、规则集地址形式、末尾唯一 `MATCH` |
| `scripts/check_upstream.py` | 按原生配置去重并发 GET 上游规则，区分 HTTP、网络与内容检查结果 |
| `tests/test_check_upstream.py` | 检查工具的离线网络边界、内容、命令行与并发上限测试 |
| `tests/test_validate_rules.py` | 上述校验器的回归测试 |
| `tests/test_shadowrocket_config.py` | 原生配置的策略、顺序和清单一致性测试 |
| `tests/test_service_exceptions.py`、`tests/test_bilibili_routing.py` | Lark 与 BiliBili 国际站的最小上游样本分流回归，不是完整客户端引擎 |
| `tests/test_shopping_routing.py` | 拼多多、苏宁直连与苏宁优先于 Google 关键词的回归 |
| `tests/test_vipshop_dewu_routing.py` | 唯品会与得物国内主域名直连、后缀边界及国际站不扩展的回归 |

## 本地验收

将 `shadowrocket.conf` 传到 iPhone，在 Shadowrocket 中通过文件导入入口导入并启用。不同版本的文件入口可能不同，也可尝试从“文件”应用分享给 Shadowrocket。

保留原配置以便切换回去。选择已有的可用代理节点，将全局路由设为“配置”。`PROXY` 使用客户端选择的节点，不需要自定义代理分组。

首次使用需要联网下载远程规则集。检查下载成功后，打开斗鱼和境外应用，通过连接记录确认斗鱼命中 `DIRECT`，境外规则命中 `PROXY`。仅能打开网页不代表分流正确。

本地文件不等于 HTTPS 下载链接；尚未发布的文件不能通过远程配置地址添加。

## 规则集来源

应用分类的规则集取自 [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script)，该仓库按应用分类并随上游更新。本项目主要维护应用与策略映射，也维护少量有依据的本地域名补充和服务例外，覆盖边界见下文。

## 维护说明

修改应用映射时同时更新 `shadowrocket.conf` 与历史清单 `rules.yaml`，再用 Python 3 测试（无额外依赖）：

```bash
python scripts/validate_rules.py
python -m unittest discover -s tests -v
```

测试覆盖简化清单结构、配置节、策略、顺序、斗鱼直连及两份清单的一致性，不是 Shadowrocket 官方解析器，不联网检查 URL。配置导入、远程规则下载与实际分流仍需在设备上验证。

新增规则集前先确认上游路径存在：

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/Gemini/Gemini.list
```

确认返回 `200` 且内容为有效规则后再引用。

## 上游联网检查

Python 3 标准库工具，无需安装依赖。从完整原生配置的 `[Rule]` 中提取 `RULE-SET` 地址并去重，只发 GET，不改配置、不下载落盘、不访问规则中列出的应用域名：

```bash
python scripts/check_upstream.py
python scripts/check_upstream.py --config shadowrocket.conf --workers 4 --timeout 15 --json
```

默认检查仓库内 `shadowrocket.conf`，与当前工作目录无关；不解析历史 `rules.yaml`。终端模式显示每个集合的状态、HTTP 状态、规则数和摘要；`--json` 输出包含 UTC 检查时间、计数、URL、HTTP 状态、响应大小及完整响应的 SHA-256，适合保存检查证据。不会输出服务器正文、代理凭据或异常原文。

| 结果 | 含义 |
| --- | --- |
| `ok` | HTTP 200 且通过支持范围内的基本内容检查；不代表业务可用或分流正确 |
| `not_found` | 本次 GET 返回 404/410，只说明该规则文件响应，不判定软件或整个域名失效 |
| `access_denied` / `rate_limited` | 401/403 / 429，需要核查访问条件或限流 |
| `redirect` / `http_error` | 重定向未跟随 / 其他非 200 响应，保留具体 HTTP 状态 |
| `timeout` / `tls_error` / `network_error` | 超时、证书/TLS、DNS/连接/读取异常；可达性未确认，不归为死链 |
| `invalid_content` | HTML、空列表、非 UTF-8 或支持类型的明显结构错误 |
| `content_unverified` | 出现未支持的规则类型，需人工复核，既不报成功也不直接判非法 |
| `too_large` | 响应超过 2 MiB，停止读取并标记未完成检查 |

退出码：全部 `ok` 为 0；任一项需关注为 1；参数或输入配置错误为 2；中断为 130（正在执行的请求可能需要等待超时才能退出）。输出按配置地址顺序排列，不按请求完成顺序跳动。

并发默认 4、可选 1–8；最多 256 个不同地址。超时范围 0.1–60 秒，默认 15 秒，是阻塞网络操作超时，不是整轮硬截止时间；DNS 或持续缓慢返回可能令总耗时更长。每个 URL 仅请求一次，不自动重试。最多读取 2 MiB + 1 字节判断超限。

仅接受无凭据、查询参数和 fragment 的 `https://raw.githubusercontent.com/.../*.list`，不跟随重定向；保持默认 TLS 证书校验及系统代理。它是本仓库维护工具，不是任意 URL 探测器。

内容检查支持 DOMAIN、DOMAIN-SUFFIX、DOMAIN-KEYWORD、USER-AGENT、IP-CIDR、IP-CIDR6、IP6-CIDR、IP-ASN 的基础字段检查；IP-CIDR 同时接受 IPv4/IPv6，兼容当前 Shadowrocket 上游写法。支持 IP 规则的 `no-resolve`。这不是官方完整语法解析器，不验证域名归属、优先级冲突、实机下载或每个应用的真实路由。原有离线测试仍不联网；联网命令是显式独立操作。

网络行为参考 [Python urllib.request 文档](https://docs.python.org/3/library/urllib.request.html) 和 [HTTPError/URLError 文档](https://docs.python.org/3/library/urllib.error.html)。

## 结构约定

分类规则集在前，`GEOIP,CN` 与 `DOMAIN-SUFFIX,cn` 兜底，原生配置以唯一的 `FINAL,PROXY` 收尾。历史清单的 `MATCH` 对应 `FINAL`，`🔰 选择节点` 对应 `PROXY`。

规则按顺序匹配，不是按 iOS 应用进程判断，不能保证所有国内/境外软件都被准确分类。更具体的服务例外在公司级规则集之前，避免被提前命中。

### 国际版 Lark 专属域名例外

`larksuite.com`、`larksuitecdn.com` 及其子域明确使用 PROXY，放在所有远程集合之前；国内飞书 `feishu.cn`、`feishucdn.com` 仍按已有 ByteDance 集合直连。两份配置清单同步维护，回归测试防止例外被移至 ByteDance 之后。

2026-10-23 实际 GET 核实：[ByteDance 上游](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/ByteDance/ByteDance.list) 同时收录上述四个域名；[Lark 官方网络允许列表](https://www.larksuite.com/hc/ja-JP/articles/360044784554) 列出两个 Lark 专属域名。这里的 PROXY 是本项目的分流策略，不是官方对代理的要求。

只修复这两个已确认的专属域名冲突，不承诺整个 Lark 的通话、登录或共享 CDN 都走代理。共享的 `zijieapi.com` 等域名和 ByteDance 的其他海外条目未在本批改动，仍需按实际连接记录逐项判断，不能据此声明全部境外软件已正确分流。

设备验收：导入完整配置并选择已有节点，确认连接记录中这两个域名命中 PROXY，国内飞书相关域名仍为 DIRECT；保留旧配置便于切回。不需要 HTTPS 解密，不上传完整流量日志。静态测试只验证配置策略和先后关系，不替代 iPhone 验证。

### BiliBili 国际站优先代理

在国内直连集合之前引用 `BiliBiliIntl` 并指定 PROXY，避免国际站被国内 `BiliBili` 集合提前直连。国内 `bilibili.com` 及其子域仍走 DIRECT，既有斗鱼和 Lark 规则不变。

2026-10-27 实际 GET 核实：[BiliBili 上游](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/BiliBili/BiliBili.list) 的 127 条有效规则包含 `DOMAIN-SUFFIX,bilibili.tv`；[BiliBiliIntl 上游](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/BiliBiliIntl/BiliBiliIntl.list) 当前仅有这一条有效规则。因此本批确认修复的是 `bilibili.tv` 及其子域的优先级冲突，不保证国际版所有登录、视频 CDN 或共享域名均被覆盖；如 `biliintl.com` 等其他域名未在本批修改。上游 master 会变化，后续维护需重新核对内容。

离线测试使用上述最小域名样本验证两份配置的策略和顺序，包含移除或后移例外后重现错误直连的对照测试；不下载实时集合、不模拟 UA/IP 等其他匹配，也不证明服务可用或地区解锁。

设备验收：保留旧配置，导入完整 `shadowrocket.conf`、选择已有节点并使用“配置”路由，刷新远程规则集并确认下载成功。分别访问 `www.bilibili.tv` 与 `www.bilibili.com`，在连接记录中核对前者命中 BiliBiliIntl / PROXY，后者命中 BiliBili / DIRECT；同时回归斗鱼 DIRECT 和 Lark 专属域名 PROXY。网页能打开不等于分流正确，无需 HTTPS 解密或上传完整日志。本批尚未经过 iPhone 实机验证。

### 拼多多与苏宁直连

国内集合新增 [Pinduoduo](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/Pinduoduo/Pinduoduo.list) 与 [SuNing](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/SuNing/SuNing.list)，均使用 DIRECT，位于境外代理集合及兜底之前。2026-10-27 实际 GET 为 200，有效规则分别为 3 条和 31 条，均为域名后缀规则。拼多多涵盖 `pinduoduo.com`、`yangkeduo.com`、`pddpic.com`；苏宁涵盖主站及其上游列出的关联服务，不表示逐个域名都经设备验证。

同日核对现有 23 个远程集合：其域名规则未覆盖拼多多这 3 个后缀；苏宁的 12 个 `.cn` 后缀已有兜底直连，其余 19 个后缀未被既有远程域名规则直连覆盖。其中 `suningmail.com` 包含 `gmail`，会匹配 [Google 上游](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/Google/Google.list) 的 `DOMAIN-KEYWORD,gmail`，因此苏宁集合必须优先；真正的 `gmail.com` 仍走代理。域名覆盖差异不等于旧版所有实际流量都走代理：此前也可能命中国内 IP 兜底。未发现这些后缀与已引用国际集合的其他域名匹配冲突，但此核对不证明所有子域、IP 或共享服务的归属。

验收：导入完整配置、刷新两组远程规则后，打开拼多多和苏宁，检查相关连接记录为 DIRECT；可核对 `pinduoduo.com`、`pddpic.com`、`suning.com`、`suningcdn.com` 等实际出现的域名。若观察到 `suningmail.com`，应优先命中 SuNing / DIRECT；无需为测试登录邮箱或提供私人日志。同时回归 BiliBili 国际站、Lark 及 Gmail 的代理策略。本地测试仅使用最小域名样本，不模拟 DNS/GEOIP/UA 或证明购买、支付等全部业务可用；iPhone 实机验证仍待完成。

### 唯品会与得物国内主域名直连

2026-10-30 实际 GET 核实 [VipShop 上游](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/VipShop/VipShop.list) 返回 200，包含 4 条 DOMAIN-SUFFIX：`appsimg.com`、`appvipshop.com`、`vip.com`、`vipstatic.com`。新增该集合 DIRECT，并手写 `DOMAIN-SUFFIX,dewu.com,DIRECT`；两者位于境外代理集合和兜底之前。

[得物官网](https://www.dewu.com/) 的主站、商家后台及开放平台使用 `dewu.com` 及其子域，官网另将国际卖家入口链接到 `poizon.com`。本批仅补国内主域名，不添加 `poizon.com` 直连，也不猜测其他图片、支付、登录或共享 CDN 域名。DIRECT 是本项目策略，不是官网的网络要求。

同日读取原有 25 个远程集合，按 DOMAIN、DOMAIN-SUFFIX、DOMAIN-KEYWORD 核对上述 5 个主域名，未发现已有直接域名匹配；这不等于旧版流量一定走代理，国内 IP 仍可能命中 GEOIP 直连。检查不覆盖全部子域、IP、UA 或复杂规则，也不保证上游未来内容不变。

设备验收：导入完整 `shadowrocket.conf`、选择已有节点、使用“配置”路由并刷新远程规则，确认 VipShop 下载成功。打开唯品会和得物，在连接记录里查看实际出现的目标域名及最终策略：上述唯品会域名应命中 VipShop / DIRECT，`dewu.com` 子域应命中本地 DOMAIN-SUFFIX / DIRECT。若仅命中 GEOIP/CN，不能算新增域名规则验证通过；能打开或速度快慢也不能证明分流正确。没有出现的域名标记为未验证，不为测试登录或下单。

同时回归斗鱼、拼多多、苏宁 DIRECT，以及 BiliBili 国际站和 Lark 专属域名 PROXY。保留旧配置便于切回，无需 HTTPS 解密；反馈只需脱敏后的目标域名、命中规则及策略，不提供完整流量日志。本批离线测试使用最小域名样本，不替代 Shadowrocket 引擎或 iPhone 实测。

## License

MIT
