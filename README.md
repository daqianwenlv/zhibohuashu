<!-- 这是什么：直播话术（zhibohuashu）代码仓说明；谁用：接手 y1.wcc.cn/workspace/zhubo/ 的人和 AI；什么时候改：目录结构或部署位置变了 -->

# 直播话术

线上地址：https://y1.wcc.cn/workspace/zhubo/ （大千 AI 办公室内，需登录）

主播用的直播话术页：按项目读在售商品、项目档案和平台规则，生成场景话术、产品话术和整场脚本；每段台词可以用指定声音配音，也可以上传主播真人录音替换。

## 目录

| 仓内路径 | 线上位置（y1y1） | 说明 |
|---|---|---|
| `web/index.html` | `/var/www/y1-home/workspace/zhubo/index.html` | 页面（单文件） |
| `web/data/index.json` | `/var/www/y1-home/workspace/zhubo/data/index.json` | 项目清单 |
| `backend/gen.py` | `/opt/ai-office/zhubo/gen.py` | 话术生成脚本：`python3 gen.py --project <项目id>`，输出 `data/<项目id>.json` |
| `backend/zhubo_api.py` | 摘自 `/opt/ai-office/auth_server.py` | 配音 / 预生成 / 录音上传接口（只读参考，线上跑在 auth_server.py 里，端口 5080） |
| `skill/` | `/var/www/y1-home/workspace/skills/zhibo-huashu/` | 「直播话术」技能，gen.py 生成时读它 |

## 不在仓里的

- 生成好的话术 `data/<项目>.json`、配音 `audio/*.mp3`：运行产物
- 商品、知识库等原始资料（`/opt/ai-office/zhubo/data/`）：业务数据
- `auth_server.py` 全文：办公室共用服务，含其他应用与内部地址

本仓是公开仓，只放代码和技能文本。
