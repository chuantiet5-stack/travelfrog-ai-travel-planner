# 四季个性化旅游景点推荐系统

Python 程序设计课程设计基础版，采用 Flask + SQLite + HTML/CSS/JavaScript。

## 功能

- 四季主题首页与 20 条初始景点数据
- 五维用户偏好采集
- 30/30/20/10/10 标签匹配评分
- Python 函数生成个性化推荐理由
- 推荐结果排序、收藏与景点详情
- 用户注册、登录和安全密码哈希
- 个人中心、浏览记录、数据库收藏和景点评论
- 管理员景点新增、修改和删除
- 管理员/普通用户角色权限隔离
- 管理后台统计、用户数据、偏好数据和评论管理
- 用户偏好与推荐记录写入 SQLite

## 默认管理员

首次执行 `init_db.py` 会增量创建管理员角色，不会清空原有数据。

```text
用户名：admin
密码：admin123
```

管理员登录后自动进入管理后台；普通用户即使手动访问 `/admin` 也会被权限检查拦截。正式部署时可通过环境变量 `TRAVEL_ADMIN_USERNAME` 和 `TRAVEL_ADMIN_PASSWORD` 设置不同的初始管理员。

## 运行步骤

```powershell
cd D:\桌面\1
python -m pip install -r requirements.txt
python init_db.py
python app.py
```

浏览器访问：`http://127.0.0.1:5001`

也可以直接双击 `启动旅游系统.bat`。

## 主要文件

```text
1/
├─ app.py
├─ init_db.py
├─ travel.db
├─ templates/
│  ├─ index.html
│  ├─ recommend.html
│  ├─ result.html
│  ├─ detail.html
│  ├─ admin.html
│  ├─ login.html
│  ├─ profile.html
│  └─ base.html
├─ static/
│  ├─ css/style.css
│  └─ js/main.js
└─ tests/test_app.py
```

测试命令：

```powershell
python -m unittest discover -s tests -v
```
