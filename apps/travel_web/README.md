# 景点推荐网站

TravelFrog 的 Web 应用，采用 Flask、SQLite 和 HTML/CSS/JavaScript。

## 功能

- 按季节、风格、预算、天数及同行人群采集偏好。
- 城市与景点推荐、匹配评分与推荐理由。
- 注册登录、收藏、评论、浏览记录与个人中心。
- 管理员维护景点、用户及推荐记录。

## 启动

从仓库根目录执行：

```bash
cd apps/travel_web
python -m pip install -r requirements.txt
python init_db.py
python app.py
```

访问 <http://127.0.0.1:5001>。

## 数据与管理员

`init_db.py` 创建表、初始景点与管理员。默认管理员为 `admin / admin123`；初始化前可使用 `TRAVEL_ADMIN_USERNAME` 和 `TRAVEL_ADMIN_PASSWORD` 设置本地账号。

数据库在本地生成，由 `.gitignore` 排除。地图 SDK 和地图 REST 查询分别通过 `AMAP_WEB_KEY` 与 `AMAP_REST_KEY` 环境变量配置。

## 测试与文档

```bash
python -m unittest discover -s tests -v
```

- [项目首页](../../README.md)
- [配置指南](../../docs/configuration.md)
- [开发与测试](../../docs/development.md)
