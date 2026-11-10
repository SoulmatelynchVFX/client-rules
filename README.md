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
| `tests/test_eleme_didi_routing.py` | 饿了么与滴滴主域名直连、原有 .cn 兜底及国际服务不扩展的回归 |

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

### 饿了么与滴滴主域名直连

新增 [Eleme 上游集合](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/Eleme/Eleme.list) DIRECT，以及 `DOMAIN-SUFFIX,didichuxing.com,DIRECT`，放在境外代理集合和兜底之前。滴滴的 [官方 MCP 服务](https://mcp.didichuxing.com/) 使用该主域名下的地址；这里的 DIRECT 是本项目策略，不是服务方对网络的要求。

2026-11-03 实际 GET 核对现有 26 个集合和 Eleme、DiDi 两个候选，28 个响应均为 HTTP 200 且通过基本内容检查。Eleme 含 13 个域名后缀；原配置的 `.cn` 兜底已覆盖其中 6 个，另外 7 个（如 `ele.me`、`elemecdn.com`）及 `didichuxing.com` 未被既有域名规则覆盖。包括 Alibaba 在内的现有远程集合，未发现与这些目标的域名规则重叠。此次核对不包含 DNS、IP 或 UA 匹配，因此不能推断旧版实际流量一定走代理。

[DiDi 上游集合](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/DiDi/DiDi.list) 的 25 个后缀还包含 `didi-food.com`、`didiaustralia.blog`、`didimobility.co.jp` 和 `didiglobal.com` 等国际或共享服务。本批采用主域名补充，不将整个集合设为 DIRECT，也不增加上述域名的专属规则；其余服务沿用原有配置。后续按实际使用中出现的域名再扩展，不把本次补充称为滴滴所有业务的完整覆盖。

验收：导入完整 `shadowrocket.conf`，选择已有节点并使用“配置”路由，刷新远程规则并确认 Eleme 下载成功。打开饿了么和滴滴，在连接记录中核对实际出现的 `ele.me`、`elemecdn.com` 等域名命中 Eleme / DIRECT，`didichuxing.com` 子域命中本地 DOMAIN-SUFFIX / DIRECT。没有出现的域名记为未验证；不需要下单、支付或上传完整日志。同时回归 Lark、BiliBili 国际站 PROXY 和原有国内服务 DIRECT。

本地测试包含根域名、子域名、相似域名边界、移除新增规则的对照、优先级及两份清单的一致性。它只回放已核对的域名样本，iPhone 实机验证另行完成。

### 高德与 12306 覆盖核对

2026-11-06 实际 GET 核对原有 27 个远程集合及 [GaoDe](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/GaoDe/GaoDe.list)、[12306](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/12306/12306.list) 两个候选，29 个响应均为 HTTP 200 并通过基本规则内容检查。

本批新增 GaoDe 集合 DIRECT，位于境外代理集合和兜底之前。核对时包含 9 个后缀：`a-map.cn`、`a-map.co`、`a-map.link`、`a-map.vip`、`amap.com`、`amapauto.com`、`anav.com`、`autonavi.com`、`gaode.com`。按既有集合的 DOMAIN / DOMAIN-SUFFIX / DOMAIN-KEYWORD 比较，未发现这些主域名的匹配；其中 a-map.cn 已有 .cn 兜底直连，其他 8 个新增明确域名覆盖。没有执行 DNS、IP 或 UA 回放，不能据此断言此前一定走代理；可能已有 GEOIP 国内 IP 直连。

12306 候选含 15 个后缀，9 个 .cn 已有直连兜底，包括 `12306.cn` 及其子域。另 6 个为 `95572.com`、`china-ric.com`、`crct.com`、`nntlj.com`、`peoplerail.com`、`tdpress.com`；没有实机证据证明它们是 12306 App 的必要流量，因此本批**不整组引入 12306 集合、不添加重复的 12306.cn 规则**，其余域名沿用现有策略。此结论不是“12306 全业务已验证”，若实机发现错误分流，再按脱敏连接记录补充。

设备验收：保留旧配置，导入完整 `shadowrocket.conf`，使用已有节点和“配置”路由，刷新远程规则并确认 GaoDe 下载成功。打开高德，在连接记录中核对实际出现的 `amap.com`、`autonavi.com` 等主机命中 GaoDe / DIRECT；12306 的 `12306.cn` 子域应为 DIRECT，可能命中 .cn 或更早的 GEOIP/CN。只看能否打开或速度快慢不能判定策略。未出现的域名记为未验证；不为测试登录、下单或上传完整日志，不需要 HTTPS 解密。

同时回归斗鱼、拼多多、苏宁 DIRECT，以及 Lark、BiliBili 国际站 PROXY。离线测试仅回放核实的域名样本、后缀边界及顺序，不替代 Shadowrocket 引擎或 iPhone 实测。Apple Relay 指定主机策略与验收方式见对应章节。

### 安居客与前程无忧直连

新增 [Anjuke](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/Anjuke/Anjuke.list) 与 [51Job](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/51Job/51Job.list) 两组 DIRECT，放在境外代理集合与兜底之前。2026-11-10 实际 GET：Anjuke 含 7 条、51Job 含 19 条，均为 DOMAIN-SUFFIX；两组是按上游应用分类引入，不代表每个关联域名的归属、业务或实机行为都经过独立验证。

同日核对原有 28 个集合及两个候选，30 个均 HTTP 200、基本规则内容检查通过。按原有集合 DOMAIN / DOMAIN-SUFFIX / DOMAIN-KEYWORD 比较候选的 26 个主域名，未发现已有匹配，包括境外代理集合；其中 5 个 .cn 后缀已有直连兜底，另外 21 个补充明确域名覆盖。未检查全部子域、DNS、IP 或 UA，不能据此认定旧配置流量一定走代理；仍可能原本命中 GEOIP/CN 直连。上游 master 内容可能变化。

Anjuke 当前包含 anjuke.com、anjukestatic.com、aifcdn.com 等；51Job 包含 51job.com、51jobcdn.com、yingjiesheng.com 等及上游列出的关联服务。本批不扩大到整个 58、IBM 等公司域名，也不按名称猜测未列出的登录、招聘或共享 CDN；遇到国际/共享服务疑似错误分流，应依据实际连接记录逐项调整，不能宣称这两款 App 全业务均已验证。

验收：保留旧配置，导入完整 shadowrocket.conf，选择已有节点并使用“配置”路由；刷新远程规则，确认 Anjuke 与 51Job 下载成功。打开两款软件，在连接记录中核对实际出现的 anjuke.com/anjukestatic.com 与 51job.com/51jobcdn.com 子域，分别应命中相应集合 / DIRECT。仅能打开或速度变化不足以证明命中，未出现的主机标为未验证；不为验证登录、投递简历、上传个人资料或支付，不需 HTTPS 解密与完整流量日志。

同时回归高德、斗鱼、拼多多与苏宁 DIRECT，以及 Lark、BiliBili 国际站 PROXY。离线测试仅回放已核对的域名样本、后缀边界与配置顺序；不替代 Shadowrocket 引擎及 iPhone 实机验证。Apple Relay 的指定主机策略见下节。

### Apple 智能扩展与私有云计算：两个指定主机优先代理

两份清单最前面增加精确规则 `DOMAIN,apple-relay.apple.com,PROXY` 和 `DOMAIN,apple-relay.fastly-edge.com,PROXY`，历史清单映射到对应节点策略。仅匹配这两个主机，不包含其子域；已有国内应用分流、OpenAI 集合、DNS、bypass-system 与局域网设置沿用原值。

2026-11-04 核对 [Apple 企业网络文档](https://support.apple.com/en-ie/101555)：前者用于 Apple Intelligence Extensions，后者用于 Private Cloud Compute，均列出 TCP/UDP 443。此处是本项目分流策略，不是完整 Apple 智能服务主机清单或官方地区解锁办法；未添加 HTTPS 解密、共享 IP 段或其他 PCC 主机。

原配置已有 FINAL/PROXY，缺少精确规则不代表此前一定直连；未命中更早规则且遇到 GEOIP/CN/DIRECT 时才可能提前直连。新增规则保证被配置接管并识别为这两个域名的连接优先匹配 PROXY，不保证系统全部流量已被接管。本地测试覆盖精确边界、优先级、条件性 GEOIP 回退及两份清单一致性，不模拟 iOS 地区资格。

“地区不可用”不能据此确定为缓存问题；退出设置等待 15 秒或改代理能否解决尚无设备证据。[OpenAI 设置说明](https://help.openai.com/en/articles/10269382-setting-up-chatgpt-with-apple-intelligence) 仍要求 Apple Intelligence 与 ChatGPT 均满足支持条件。本配置不修改定位、IP 地址跟踪、账户地区或设备语言。

验收：保留旧配置，导入完整 shadowrocket.conf，选择已有节点并使用“配置”路由，保持系统设置不变重新尝试 ChatGPT 扩展。可选择不登录账户进行首次验证，使用不含私人信息的请求。在连接记录中查看实际出现的两个主机是否分别命中 DOMAIN / PROXY；速度或仅命中 FINAL 不能证明新增规则生效，未出现记为未验证。不需要 HTTPS 解密或完整日志。

若命中 PROXY 后仍有地区提示，反馈准确提示、iOS/Shadowrocket 版本、设备与 Siri 语言、Apple 账户地区与当前国家/地区即可；无需账户凭据、订阅地址、精确位置。没有相关记录时先检查配置是否启用及流量接管，不盲目扩大 Apple 规则。回归国内服务 DIRECT 和 Lark、BiliBili 国际站 PROXY，异常可切回旧配置。配置发布不代表已经 iPhone 实测或成功解除地区限制。

## License

MIT
