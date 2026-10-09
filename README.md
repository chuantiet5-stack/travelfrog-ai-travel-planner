# 智能旅行助手 · TravelFrog

基于 NanoClaw Agent 的个性化智能旅行规划系统，包含旅行对话助手与旅游景点推荐网站。

## 功能与技术栈

- 多轮旅行对话，通过 Agent 工具调用连接景点推荐、地图搜索、天气查询与图片服务。
- 景点网站根据季节与用户偏好计算推荐，支持注册登录、收藏、评论和管理员管理。
- 支持 Web、飞书与 QQ 交互渠道。
- 技术栈：Python、NanoClaw Agent、OpenAI 兼容模型接口、MCP、Flask、SQLite、HTML/CSS/JavaScript。

## 项目结构

- `TravelFrog/`：Agent、Web/飞书/QQ 渠道、地图与天气 MCP 工具。
- `travel-recommend-system-main/`：Flask + SQLite 景点推荐网站，提供偏好采集、景点推荐、收藏与管理页面。

## 本地启动

建议为两个子项目分别创建 Python 虚拟环境，在各自目录安装原有 `requirements.txt`。这些依赖文件沿用交付版本。

旅行助手：

```powershell
cd TravelFrog
python -m pip install -r requirements.txt
Copy-Item config.example.json config.json
# 编辑 config.json，填入自己的模型 API 密钥；地图、天气及 IM 凭证按需配置。
python main.py
```

助手 Web 服务默认端口为 `8081`。配置示例中的 MCP 启动命令使用 `python`，请确保它指向当前虚拟环境。

景点推荐网站：在另一个终端从仓库根目录运行。

```powershell
cd travel-recommend-system-main
python -m pip install -r requirements.txt
python init_db.py
python app.py
```

网站默认访问地址为 `http://127.0.0.1:5001`，详细功能与数据库初始化说明见该目录的 README。网页中的地图 API 密钥已清空，需要在本地自行配置。

## 发布说明

公开版本仅保留源码和运行所需资源。原始 API 密钥、机器人凭证、聊天记录、用户数据库、日志和缓存均未提交；视频、PPT 和原始压缩包不上传。`config.json` 为本地私有配置，使用 `config.example.json` 创建。

本次整理验证了发布文件及 Python 语法，未安装完整依赖或执行联网业务测试。
