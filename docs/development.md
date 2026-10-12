# 开发与测试

## 开发环境

进入对应应用目录后，创建独立虚拟环境：

```bash
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
```

Linux/macOS：

```bash
source .venv/bin/activate
```

安装该应用目录中的依赖文件后再运行。配置、数据库与会话均在本地生成。

## 依赖选择

`requirements.txt` 是根目录依赖入口，引用两个服务的依赖文件。Agent 依赖已按源码直接导入的包整理；原开发环境完整快照保存在 `requirements/legacy-agent-environment.txt`，仅供历史参考。两个服务也可使用各自的虚拟环境。

## 代码阅读入口

| 路径 | 职责 |
| --- | --- |
| `apps/travel_agent/main.py` | 组装模型、工具、渠道和消息网关 |
| `apps/travel_agent/agent/loop.py` | Agent 迭代与旅行状态管理 |
| `apps/travel_agent/agent/tools/mcp_server.py` | MCP 客户端与工具注册 |
| `apps/travel_agent/session/manager.py` | 会话与旅行状态持久化 |
| `apps/travel_web/recommendation/` | 候选筛选、偏好匹配与权重计算 |
| `apps/travel_web/app.py` | 网站路由、用户功能与管理后台 |

## 自动化测试

在已安装网站依赖的环境中执行：

```bash
cd apps/travel_web
python -m unittest discover -s tests -v
```

`test_app.py` 包含网站行为与评分断言；其余文件提供推荐算法与偏好解析的验证脚本。Agent 目录中的 `test_amap.py`、`test_mcp.py` 等为工具验证脚本，需先核对相关服务与凭证。

## 联动验证

1. 启动网站，检查注册登录、偏好提交、景点详情与收藏。
2. 启动 Agent，输入包含目的地、天数和同行人数的旅行请求。
3. 观察地图与天气工具返回值，检查旅行状态是否随对话更新。
4. 在有地图配置的环境中检查网页地图、地点检索与路线展示。

修改业务逻辑时，为可独立验证的推荐算法或网站行为补充测试；联网工具单独验证。提交前检查变更中不含本地凭证与运行数据。
