<!-- 这是什么：直播话术（zhibohuashu）代码仓说明；谁用：接手 y1.wcc.cn/workspace/zhubo/ 的人和 AI；什么时候改：目录结构或部署位置变了 -->

# 直播话术

线上地址：https://y1.wcc.cn/workspace/zhubo/ （大千 AI 办公室内，需登录）

主播用的直播话术页：按项目读在售商品（来客实时）、项目档案和平台规则，由 AI 生成场景话术（开场、讲景区、讲品、促单、答疑、留人、救场、讲福利、过品、下播……）、常见问题回答、产品话术和整场脚本；转成语音后主播只管点播放。

页面上能做的：

- **每条台词有编号**（#12），能改、能删（可撤销）、能「自己写一版」；改的东西自动保存（服务器 + 本机各一份）
- **AI 再写一版**：每个场景 / 商品 / 整场段落下面可以带一句要求（「再快一点」「讲亲子」）让 AI 现场补一版
- **评论区来问**：把观众的问题粘进来，AI 写回答、存进「常见问题」并自动转语音
- **快捷键**：任意台词可放到数字键 1–9（默认放常见问题前 9 条），直播时按数字直接播，再按暂停，Esc 停
- **语速**：1.0–1.5×，只改播放速度不变调（配音念得比真主播慢，默认 1.2×）
- **自己填景区资料**（资料页）：「AI 再写一版」「AI 写回答」和下次整套生成都会读
- 转语音可整套、可单条，选主播声音；也可以拖 / 传主播真人录音替换某一条

## 目录

| 仓内路径 | 线上位置（y1y1） | 说明 |
|---|---|---|
| `web/index.html` | `/var/www/y1-home/workspace/zhubo/index.html` | 页面（单文件） |
| `web/data/index.json` | `/var/www/y1-home/workspace/zhubo/data/index.json` | 项目清单 |
| `backend/gen.py` | `/opt/ai-office/zhubo/gen.py` | 话术生成脚本：`python3 gen.py --project <项目id>`，输出 `data/<项目id>.json`；`--one` 从 stdin 读一段请求，写一段（再写一版 / 回答评论区问题） |
| `backend/zhubo_api.py` | 摘自 `/opt/ai-office/auth_server.py` | 配音 / 预生成 / 录音上传 / 自己改的存取 / AI 单段生成接口（只读参考，线上跑在 auth_server.py 里，端口 5080） |
| `skill/` | `/var/www/y1-home/workspace/skills/zhibo-huashu/` | 「直播话术」技能，gen.py 生成时读它 |

## 上线这一版要做的

1. `web/index.html`、`backend/gen.py` 照上表覆盖到线上
2. 把 `backend/zhubo_api.py` 里「新增」那一段（`zb_mine_*`、`zb_gen`、`zb_pregen_start` 的 `texts` 参数）和对应路由（`GET/POST /api/zhubo/mine`、`POST /api/zhubo/gen`、pregen 带 `texts`）合进 `auth_server.py`，重启
3. 自己改的存在 `/opt/ai-office/zhubo/data/<项目>_mine.json`（不在网站目录下）

接口没合进去之前，页面照样能用：改动先存在本机浏览器（顶栏会提示「没存到服务器」），「AI 再写一版」「AI 写回答」会提示失败。

## 不在仓里的

- 生成好的话术 `data/<项目>.json`、自己改的 `<项目>_mine.json`、配音 `audio/*.mp3`：运行产物
- 商品、知识库等原始资料（`/opt/ai-office/zhubo/data/`）：业务数据
- `auth_server.py` 全文：办公室共用服务，含其他应用与内部地址

本仓是公开仓，只放代码和技能文本。
