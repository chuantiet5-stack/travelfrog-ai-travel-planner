# 配置指南

## Agent 配置

从 `apps/travel_agent/config.example.json` 创建同目录的 `config.json`。

| 字段 | 说明 |
| --- | --- |
| `api_key` | 模型服务密钥，可由环境变量 `NANOCLAW_API_KEY` 覆盖 |
| `base_url` | OpenAI 兼容接口地址 |
| `models.main / subagent / cheap` | 对应任务使用的模型名称 |
| `web.enabled / host / port` | Web 渠道设置，示例端口为 `8081` |
| `amap.api_key` | 地图 MCP 服务的高德 REST API Key |
| `seniverse.api_key` | 天气 MCP 服务的心知天气 API Key |
| `feishu.app_id / app_secret` | 飞书渠道凭证，留空时不启用 |
| `qq.app_id / app_secret` | QQ 渠道凭证，留空时不启用 |
| `mcp_servers` | 工具服务的启动命令与参数 |

MCP 示例使用 `python` 启动子进程。请在已激活的虚拟环境中运行，或将 `command` 改为该环境的 Python 绝对路径。

## 景点网站环境变量

在启动 `apps/travel_web/app.py` 前设置：

| 环境变量 | 用途 |
| --- | --- |
| `TRAVEL_DATABASE` | SQLite 文件路径，默认使用项目本地数据库 |
| `FLASK_SECRET_KEY` | 网站会话签名密钥 |
| `TRAVEL_ADMIN_USERNAME` | 初始化管理员账号，默认 `admin` |
| `TRAVEL_ADMIN_PASSWORD` | 初始化管理员密码，默认 `admin123` |
| `AMAP_WEB_KEY` | 网页地图 SDK 的浏览器 Key |
| `AMAP_REST_KEY` | 页面地理编码与地点查询的 REST API Key |
| `FLASK_DEBUG` | 设置为 `1` 时启用本地调试模式 |

Windows PowerShell 示例：

```powershell
$env:AMAP_WEB_KEY = "填写自己的浏览器地图Key"
$env:AMAP_REST_KEY = "填写自己的REST地图Key"
python app.py
```

Linux/macOS 使用 `export AMAP_WEB_KEY=...` 和 `export AMAP_REST_KEY=...`。网页地图配置与 Agent 的 `amap.api_key` 分别读取，需要各自设置。

## 初始化与服务连接

1. 在景点网站目录执行 `python init_db.py`，创建数据库与初始景点。
2. 启动网站，确认 `http://127.0.0.1:5001` 可访问。
3. 在 Agent 目录创建并编辑 `config.json`，再启动 `main.py`。
4. 按需启用地图、天气与 IM 渠道，缺少对应凭证时不要将该渠道作为完整演示路径。

真实配置、数据库、日志和会话记录保持在本地，不提交到版本库。
