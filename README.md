# TravelFrog — 智能旅行规划助手

基于 Python 的旅行规划应用，结合多轮对话、景点推荐、地图与天气工具，提供旅行建议和景点管理功能。

## 功能

- 多轮收集目的地、出行天数、预算和同行人数，维护旅行会话状态。
- 根据用户偏好匹配城市与景点，展示推荐理由。
- 通过 MCP 调用地图、天气和景点图片工具。
- 网站提供登录注册、收藏评论、个人中心和管理后台。
- 支持 Web、命令行、飞书和 QQ 渠道。

## 技术栈

Python · Flask · FastAPI · SQLite · OpenAI 兼容接口 · MCP

## 项目结构

```text
travelfrog-ai-travel-planner/
├── apps/
│   ├── travel_agent/       # Agent、工具、渠道及配置示例
│   └── travel_web/         # Flask 网站、推荐算法及测试
├── docs/                  # 配置与开发文档
├── requirements/          # 原开发环境依赖快照
├── requirements.txt       # 项目依赖入口
├── run.py                 # 服务启动入口
├── .editorconfig
├── .gitignore
└── README.md
```

## 快速开始

```bash
git clone https://github.com/chuantiet5-stack/travelfrog-ai-travel-planner.git
cd travelfrog-ai-travel-planner
python -m venv .venv
```

激活虚拟环境（[操作说明](docs/development.md#开发环境)），然后安装依赖并创建配置：

```bash
python -m pip install -r requirements.txt
python run.py agent --init-config
```

编辑 `apps/travel_agent/config.json`，填写模型接口密钥及所需工具配置。启动网站：

```bash
python run.py init-db
python run.py web
```

网站地址：<http://127.0.0.1:5001>。在另一个终端启动 Agent：

```bash
python run.py agent
```

Agent 地址：<http://127.0.0.1:8081>。两个服务也可以分别安装各自的依赖文件，单独运行。

## 测试

```bash
cd apps/travel_web
python -m unittest discover -s tests -v
```

Agent 中的地图和 MCP 验证脚本需要相应服务和凭证。

## 文档

- [配置指南](docs/configuration.md)
- [开发与测试](docs/development.md)
- [景点网站说明](apps/travel_web/README.md)

配置示例仅保留字段结构；真实凭证、数据库与运行数据在本地生成，由 `.gitignore` 排除。
