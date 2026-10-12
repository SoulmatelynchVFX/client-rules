# client-rules

客户端用的应用分流规则片段（Clash 格式，仅含 `rules` 段），不含节点与策略分组配置。

## 文件

| 文件 | 说明 |
|---|---|
| `rules.yaml` | 分流规则本体。按应用分类，`GEOIP,CN` / `DOMAIN-SUFFIX,cn` 兜底，`MATCH` 收尾 |

## 引用方式

把订阅的「远程规则 / Remote Rule」指向：

```
https://raw.githubusercontent.com/SoulmatelynchVFX/client-rules/main/rules.yaml
```

规则里的策略名写作 `🔰 选择节点`，需与本机分组名一致；若显示为其他名称（如 `Proxy`），整体替换后再用。

## 规则集来源

应用分类的规则集取自 [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script)，该仓库按应用分类并随上游更新，因此这里只维护「哪个应用走哪个分组」这一层逻辑，不自行维护域名明细。

## 维护说明

新增规则集前先确认上游路径存在：

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/客户端/Gemini/Gemini.list
```

返回 `200` 才可引用（`DeepSeek`、`EpicGames` 等路径当前不存在）。

## 结构约定

分类规则集在前，`GEOIP,CN` 与 `DOMAIN-SUFFIX,cn` 兜底，`MATCH` 置于最后且只出现一次。
