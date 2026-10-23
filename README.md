# client-rules

用于 iOS Shadowrocket 的应用分流配置：已列出的国内应用直连，境外应用走代理，国内 IP / `.cn` 直连兜底，其余流量走代理。

## 文件

| 文件 | 说明 |
|---|---|
| `shadowrocket.conf` | Shadowrocket 原生配置，包含斗鱼直连；不含节点、订阅或 HTTPS 解密设置 |
| `rules.yaml` | 历史规则清单，保留用于对照，不是完整客户端配置 |
| `scripts/validate_rules.py` | 离线结构校验：字段、重复匹配条件、规则集地址形式、末尾唯一 `MATCH` |
| `tests/test_validate_rules.py` | 上述校验器的回归测试 |
| `tests/test_shadowrocket_config.py` | 原生配置的策略、顺序和清单一致性测试 |

## 本地验收

将 `shadowrocket.conf` 传到 iPhone，在 Shadowrocket 中通过文件导入入口导入并启用。不同版本的文件入口可能不同，也可尝试从“文件”应用分享给 Shadowrocket。

保留原配置以便切换回去。选择已有的可用代理节点，将全局路由设为“配置”。`PROXY` 使用客户端选择的节点，不需要自定义代理分组。

首次使用需要联网下载远程规则集。检查下载成功后，打开斗鱼和境外应用，通过连接记录确认斗鱼命中 `DIRECT`，境外规则命中 `PROXY`。仅能打开网页不代表分流正确。

本地文件不等于 HTTPS 下载链接；尚未发布的文件不能通过远程配置地址添加。

## 规则集来源

应用分类的规则集取自 [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script)，该仓库按应用分类并随上游更新，因此这里只维护「哪个应用走哪个分组」这一层逻辑，不自行维护域名明细。

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

## 结构约定

分类规则集在前，`GEOIP,CN` 与 `DOMAIN-SUFFIX,cn` 兜底，原生配置以唯一的 `FINAL,PROXY` 收尾。历史清单的 `MATCH` 对应 `FINAL`，`🔰 选择节点` 对应 `PROXY`。

规则按顺序匹配，不是按 iOS 应用进程判断，不能保证所有国内/境外软件都被准确分类。更具体的服务例外在公司级规则集之前，避免被提前命中。

### 国际版 Lark 专属域名例外

`larksuite.com`、`larksuitecdn.com` 及其子域明确使用 PROXY，放在所有远程集合之前；国内飞书 `feishu.cn`、`feishucdn.com` 仍按已有 ByteDance 集合直连。两份配置清单同步维护，回归测试防止例外被移至 ByteDance 之后。

2026-10-23 实际 GET 核实：[ByteDance 上游](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/ByteDance/ByteDance.list) 同时收录上述四个域名；[Lark 官方网络允许列表](https://www.larksuite.com/hc/ja-JP/articles/360044784554) 列出两个 Lark 专属域名。这里的 PROXY 是本项目的分流策略，不是官方对代理的要求。

只修复这两个已确认的专属域名冲突，不承诺整个 Lark 的通话、登录或共享 CDN 都走代理。共享的 `zijieapi.com` 等域名和 ByteDance 的其他海外条目未在本批改动，仍需按实际连接记录逐项判断，不能据此声明全部境外软件已正确分流。

设备验收：导入完整配置并选择已有节点，确认连接记录中这两个域名命中 PROXY，国内飞书相关域名仍为 DIRECT；保留旧配置便于切回。不需要 HTTPS 解密，不上传完整流量日志。静态测试只验证配置策略和先后关系，不替代 iPhone 验证。

## License

MIT
