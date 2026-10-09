"""四季个性化旅游景点推荐系统。"""

import os
import re
import sqlite3
from functools import wraps
from pathlib import Path
from typing import Any
    
from flask import (
    Flask,
    flash,
    g,
	jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from init_db import DB_PATH, init_database
from recommendation.matcher import calculate_match_score
from recommendation.city_matcher import recommend_cities
from recommendation.candidate import select_top_candidates

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__)
app.config.update(
    DATABASE=os.getenv("TRAVEL_DATABASE", str(DB_PATH)),
    SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "course-design-demo-key"),
    # 模板修改后自动生效，无需重启服务（开发阶段方便调试）
    TEMPLATES_AUTO_RELOAD=True,
)

SEASONS = ["春季", "夏季", "秋季", "冬季"]
STYLES = ["古韵文化","小桥流水","山水自然","海滨休闲","城市烟火","摄影人文","雪山度假","亲子乐园","温泉康养","极限户外","沙漠戈壁","草原牧歌"]
BUDGETS = ["低预算", "中等预算", "高预算"]
DAYS = ["1天", "2-3天", "4-5天", "一周及以上"]
PEOPLE = ["个人", "情侣", "朋友", "家庭"]
ENTRY_TYPES = {"recommend", "direct"}


def get_db():
    """获取当前请求使用的 SQLite 连接。"""
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


@app.before_request
def load_logged_in_user():
    """根据会话中的用户编号加载当前登录用户。"""
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        g.user = get_db().execute(
            "SELECT id, username, role, create_time FROM app_user WHERE id = ?",
            (user_id,),
        ).fetchone()


def login_required(view):
    """限制只有登录用户才能访问的页面。"""
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash("请先登录后再使用个人中心功能。", "error")
            return redirect(url_for("login", next=request.path))
        return view(**kwargs)

    return wrapped_view


def admin_required(view):
    """限制只有管理员角色才能访问的后台功能。"""
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash("请先登录管理员账号。", "error")
            return redirect(url_for("login", next=request.path))
        if g.user["role"] != "admin":
            flash("当前账号没有管理员权限。", "error")
            return redirect(url_for("profile"))
        return view(**kwargs)

    return wrapped_view


def split_tags(value):
    """将数据库中的多值标签转换为集合。"""
    return {item.strip() for item in re.split(r"[,，、]", value or "") if item.strip()}



def generate_recommend_reason(user_pref, spot, score=None):
    """根据用户偏好和景点标签生成自然语言推荐理由（景点风格支持多选）。"""
    if score is None:
        score, _, _, _ = calculate_match_score(user_pref, spot)
    matched = []
    if user_pref["season"] in split_tags(spot["season"]):
        matched.append(f"{user_pref['season']}出游")
    user_styles = split_tags(user_pref["style_type"])
    matched_styles = user_styles & split_tags(spot["style_type"])
    if matched_styles:
        matched.append("、".join(sorted(matched_styles)))
    if user_pref["budget_level"] in split_tags(spot["budget_level"]):
        matched.append(user_pref["budget_level"])
    match_text = "、".join(matched) if matched else "多样化旅行体验"
    style_text = "、".join(sorted(user_styles)) if user_styles else "多样化"
    return (
        f"根据你选择的{user_pref['season']}出游和{style_text}偏好，"
        f"{spot['name']}与需求的匹配度为 {score}%。这里以{spot['style_type']}为主要特色，"
        f"能够提供{match_text}相关体验，适合{user_pref['people_type']}安排"
        f"{user_pref['play_days']}行程。"
    )


def preference_from_form(form):
    """
    从网页表单获取用户旅游偏好。

    除了五个基础偏好之外，
    新增出发地 origin，
    并新增 priority 用于动态调整推荐权重。

    景点风格 style_type 支持多选（最多 4 个），
    以顿号分隔存储，例如"古韵文化、摄影人文"。
    """

    priority = {
        "origin": form.get("priority_origin", "3"),
        "season": form.get("priority_season", "3"),
        "style_type": form.get("priority_style_type", "3"),
        "budget_level": form.get("priority_budget_level", "3"),
        "play_days": form.get("priority_play_days", "3"),
        "people_type": form.get("priority_people_type", "3"),
    }

    # 景点风格多选：最多取前 4 个，顿号分隔
    styles_selected = [s.strip() for s in form.getlist("style_type") if s.strip()]

    return {
        "origin": form.get("origin", ""),
        "season": form.get("season", ""),
        "style_type": "、".join(styles_selected[:4]),
        "budget_level": form.get("budget_level", ""),
        "play_days": form.get("play_days", ""),
        "people_type": form.get("people_type", ""),
        "priority": priority,
    }


def valid_preference(pref):
    """校验偏好有效性；景点风格支持顿号分隔的多选（1-4 个，均需合法）。"""
    styles_selected = [s.strip() for s in (pref["style_type"] or "").split("、") if s.strip()]
    return (
        pref["season"] in SEASONS
        and bool(styles_selected)
        and all(s in STYLES for s in styles_selected)
        and pref["budget_level"] in BUDGETS
        and pref["play_days"] in DAYS
        and pref["people_type"] in PEOPLE
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user is not None:
        return redirect(url_for("profile"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        error = None
        if not 2 <= len(username) <= 20:
            error = "用户名长度应为 2–20 个字符。"
        elif len(password) < 6:
            error = "密码长度不能少于 6 位。"
        elif password != confirm_password:
            error = "两次输入的密码不一致。"
        elif get_db().execute(
            "SELECT id FROM app_user WHERE username = ?", (username,)
        ).fetchone():
            error = "该用户名已经存在。"

        if error:
            flash(error, "error")
        else:
            db = get_db()
            cursor = db.execute(
                "INSERT INTO app_user (username, password_hash) VALUES (?, ?)",
                (username, generate_password_hash(password)),
            )
            db.commit()
            session.clear()
            session["user_id"] = cursor.lastrowid
            flash("注册成功，欢迎加入。", "success")
            return redirect(url_for("profile"))
    return render_template("login.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user is not None:
        return redirect(url_for("profile"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT * FROM app_user WHERE username = ?", (username,)
        ).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("用户名或密码不正确。", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            target = request.args.get("next", "")
            flash("登录成功。", "success")
            if target.startswith("/"):
                return redirect(target)
            return redirect(url_for("admin") if user["role"] == "admin" else url_for("profile"))
    return render_template("login.html", mode="login")


@app.get("/logout")
def logout():
    session.clear()
    flash("你已退出登录。", "success")
    return redirect(url_for("index"))


@app.get("/profile")
@login_required
def profile():
    db = get_db()
    favorites = db.execute(
        """
        SELECT s.*, f.create_time AS favorite_time
        FROM favorite f JOIN scenic_spot s ON s.id = f.spot_id
        WHERE f.user_id = ? ORDER BY f.id DESC
        """,
        (g.user["id"],),
    ).fetchall()
    histories = db.execute(
        """
        SELECT s.id, s.name, s.city, s.season,
               MAX(h.view_time) AS view_time, COUNT(*) AS view_count
        FROM browsing_history h JOIN scenic_spot s ON s.id = h.spot_id
        WHERE h.user_id = ?
        GROUP BY s.id ORDER BY MAX(h.id) DESC LIMIT 20
        """,
        (g.user["id"],),
    ).fetchall()
    comments = db.execute(
        """
        SELECT c.*, s.name AS spot_name
        FROM comment c JOIN scenic_spot s ON s.id = c.spot_id
        WHERE c.user_id = ? ORDER BY c.id DESC
        """,
        (g.user["id"],),
    ).fetchall()
    return render_template(
        "profile.html",
        favorites=favorites,
        histories=histories,
        comments=comments,
    )


@app.route("/")
def index():
    # 首页固定展示 6 个精选景点，按指定顺序排列
    favorites = ["大理洱海", "桂林山水", "武陵源", "杭州西湖", "九寨沟", "黄山"]
    placeholders = ",".join(["?"] * len(favorites))
    spots = get_db().execute(
        f"SELECT * FROM scenic_spot WHERE name IN ({placeholders})",
        favorites,
    ).fetchall()
    # 按 favorites 列表顺序排序，保证首页展示顺序
    spots.sort(key=lambda s: favorites.index(s["name"]))
    return render_template("index.html", spots=spots)


@app.post("/api/recommend")
def api_recommend():
    """
    旅游推荐 API。

    接收用户旅游偏好，
    调用基础城市推荐算法，
    返回 Top-N 候选城市。

    city_distances 可由外部服务提供，
    例如后续由 TravelFrog + AMap MCP 计算。
    """

    data = request.get_json(silent=True) or {}

    pref = {
        "origin": data.get("origin", ""),
        "season": data.get("season", ""),
        "style_type": data.get("style_type", ""),
        "budget_level": data.get("budget_level", ""),
        "play_days": data.get("play_days", ""),
        "people_type": data.get("people_type", ""),
        "priority": data.get(
            "priority",
            {
                "origin": "3",
                "season": "3",
                "style_type": "3",
                "budget_level": "3",
                "play_days": "3",
                "people_type": "3",
            },
        ),
    }

    if not valid_preference(pref):
        return jsonify(
            {
                "success": False,
                "message": "旅游偏好参数不完整或无效。",
            }
        ), 400

    city_distances = data.get(
        "city_distances",
        {},
    )

    db = get_db()

    spots = db.execute(
        "SELECT * FROM scenic_spot"
    ).fetchall()

    cities = recommend_cities(
        pref,
        spots,
        top_n=5,
        city_distances=city_distances,
    )

    result = []

    for city in cities:

        city_data = {
            "city": city["city"],
            "score": city["score"],
            "max_score": city["max_score"],
            "avg_score": city["avg_score"],
            "coverage": city["coverage"],
            "spots": [],
        }

        for item in city["spots"]:

            spot = dict(item["spot"])

            city_data["spots"].append(
                {
                    "spot": spot,
                    "score": item["score"],
                    "details": item["details"],
                    "similarities": item["similarities"],
                    "weights": item["weights"],
                }
            )

        result.append(city_data)

    return jsonify(
        {
            "success": True,
            "origin": pref["origin"],
            "preference": pref,
            "cities": result,
        }
    )


@app.route("/recommend", methods=["GET", "POST"])
def recommend():
    if request.method == "POST":

        pref = preference_from_form(request.form)

        session["recommend_preference"] = pref

        if not valid_preference(pref):
            flash("请选择完整、有效的出游偏好。", "error")
            return render_template(
                "recommend.html",
                **option_context(),
                selected=pref,
            )

        db = get_db()

        # 保存用户偏好
        cursor = db.execute(
            """
            INSERT INTO user_preference
            (season, style_type, budget_level, play_days, people_type)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                pref["season"],
                pref["style_type"],
                pref["budget_level"],
                pref["play_days"],
                pref["people_type"],
            ),
        )

        preference_id = cursor.lastrowid

        # 查询全部景点
        spots = db.execute(
            "SELECT * FROM scenic_spot"
        ).fetchall()

        # ==========================================
        # 第一阶段：城市推荐
        # ==========================================

        cities = recommend_cities(
            pref,
            spots,
            top_n=5,
        )

        db.commit()

        return render_template(
            "city_result.html",
            cities=cities,
            preference=pref,
            preference_id=preference_id,
        )

    return render_template(
        "recommend.html",
        **option_context(),
        selected={},
    )

@app.route("/city/<city>/spots")
def city_spots(city):
    """
    查看指定城市的景点推荐。
    """

    pref = session.get("recommend_preference")

    if not pref:
        flash("请先完成旅游偏好选择。", "error")
        return redirect(url_for("recommend"))

    db = get_db()

    spots = db.execute(
        """
        SELECT *
        FROM scenic_spot
        WHERE city = ?
        """,
        (city,),
    ).fetchall()

    if not spots:
        flash(f"暂未找到“{city}”的景点数据。", "error")
        return redirect(url_for("recommend"))

    results = []

    for spot in spots:

        score, details, similarities, weights = (
            calculate_match_score(
                pref,
                spot,
            )
        )

        reason = generate_recommend_reason(
            pref,
            spot,
            score,
        )

        results.append(
            {
                "spot": spot,
                "score": score,
                "reason": reason,
                "details": details,
                "similarities": similarities,
                "weights": weights,
            }
        )

    results.sort(
        key=lambda item: (
            -item["score"],
            item["spot"]["id"],
        )
    )

    favorite_ids = set()

    if g.user is not None:
        favorite_ids = {
            row["spot_id"]
            for row in db.execute(
                """
                SELECT spot_id
                FROM favorite
                WHERE user_id = ?
                """,
                (g.user["id"],),
            ).fetchall()
        }

    return render_template(
        "city_spots.html",
        city=city,
        results=results,
        preference=pref,
        favorite_ids=favorite_ids,
    )

@app.route("/travel-agent/<city>")
def travel_agent(city):

    pref = session.get("recommend_preference")

    if not pref:
        flash("请先完成旅游偏好选择。", "error")
        return redirect(url_for("recommend"))

    db = get_db()

    spots = db.execute(
        """
        SELECT *
        FROM scenic_spot
        WHERE city = ?
        """,
        (city,),
    ).fetchall()


    if not spots:
        flash(f"暂未找到“{city}”的景点数据。", "error")
        return redirect(url_for("recommend"))


    # sqlite Row 转普通 dict
    spots_json = []

    for spot in spots:
        spots_json.append(dict(spot))

    # ===== 调试信息 =====
    print("旅蛙接收城市:", city)
    print("用户偏好:", pref)
    print("候选景点数量:", len(spots_json))

    return render_template(
        "travel_agent.html",
        city=city,
        preference=pref,
        spots=spots_json,
        entry_type="recommend",
    )

@app.route("/travel-agent")
def travel_agent_direct():
    """直接进入旅蛙，不预设目的地。"""

    # 直接进入旅蛙时，没有推荐系统产生的城市和景点；
    # 也不复用 session 中的旧偏好，避免左侧显示残留权重
    return render_template(
        "travel_agent.html",
        city="",
        preference={},
        spots=[],
        entry_type="direct",
    )

@app.route("/detail/<int:spot_id>")
def detail(spot_id):
    db = get_db()
    spot = db.execute("SELECT * FROM scenic_spot WHERE id = ?", (spot_id,)).fetchone()
    if spot is None:
        flash("景点不存在或已被删除。", "error")
        return redirect(url_for("index"))

    is_favorite = False
    if g.user is not None:
        db.execute(
            "INSERT INTO browsing_history (user_id, spot_id) VALUES (?, ?)",
            (g.user["id"], spot_id),
        )
        db.commit()
        is_favorite = db.execute(
            "SELECT id FROM favorite WHERE user_id = ? AND spot_id = ?",
            (g.user["id"], spot_id),
        ).fetchone() is not None

    preference_id = request.args.get("preference_id", type=int)
    record = None
    if preference_id:
        record = db.execute(
            """
            SELECT r.*, p.season, p.style_type, p.budget_level, p.play_days, p.people_type
            FROM recommendation r
            JOIN user_preference p ON p.id = r.preference_id
            WHERE r.preference_id = ? AND r.spot_id = ?
            """,
            (preference_id, spot_id),
        ).fetchone()
    comments = db.execute(
        """
        SELECT c.*, u.username
        FROM comment c JOIN app_user u ON u.id = c.user_id
        WHERE c.spot_id = ? ORDER BY c.id DESC
        """,
        (spot_id,),
    ).fetchall()
    return render_template(
        "detail.html",
        spot=spot,
        record=record,
        comments=comments,
        is_favorite=is_favorite,
    )


@app.post("/favorite/<int:spot_id>")
@login_required
def toggle_favorite(spot_id):
    db = get_db()
    exists = db.execute(
        "SELECT id FROM favorite WHERE user_id = ? AND spot_id = ?",
        (g.user["id"], spot_id),
    ).fetchone()
    if exists:
        db.execute("DELETE FROM favorite WHERE id = ?", (exists["id"],))
        flash("已取消收藏。", "success")
    else:
        db.execute(
            "INSERT INTO favorite (user_id, spot_id) VALUES (?, ?)",
            (g.user["id"], spot_id),
        )
        flash("景点已收藏。", "success")
    db.commit()
    target = request.form.get("next", "")
    return redirect(target if target.startswith("/") else url_for("detail", spot_id=spot_id))


@app.post("/detail/<int:spot_id>/comment")
@login_required
def add_comment(spot_id):
    content = " ".join(request.form.get("content", "").strip().split())
    if not 2 <= len(content) <= 300:
        flash("评论内容应为 2–300 个字符。", "error")
    elif get_db().execute(
        "SELECT id FROM scenic_spot WHERE id = ?", (spot_id,)
    ).fetchone() is None:
        flash("景点不存在。", "error")
        return redirect(url_for("index"))
    else:
        db = get_db()
        db.execute(
            "INSERT INTO comment (user_id, spot_id, content) VALUES (?, ?, ?)",
            (g.user["id"], spot_id, content),
        )
        db.commit()
        flash("评论发布成功。", "success")
    return redirect(url_for("detail", spot_id=spot_id))


@app.post("/comment/<int:comment_id>/delete")
@login_required
def delete_comment(comment_id):
    db = get_db()
    db.execute(
        "DELETE FROM comment WHERE id = ? AND user_id = ?",
        (comment_id, g.user["id"]),
    )
    db.commit()
    flash("评论已删除。", "success")
    return redirect(url_for("profile"))


@app.post("/history/clear")
@login_required
def clear_history():
    db = get_db()
    db.execute("DELETE FROM browsing_history WHERE user_id = ?", (g.user["id"],))
    db.commit()
    flash("浏览记录已清空。", "success")
    return redirect(url_for("profile"))


@app.route("/admin")
@admin_required
def admin():
    db = get_db()
    spots = db.execute("SELECT * FROM scenic_spot ORDER BY id DESC").fetchall()
    stats = {
        "spots": db.execute("SELECT COUNT(*) FROM scenic_spot").fetchone()[0],
        "users": db.execute("SELECT COUNT(*) FROM app_user WHERE role = 'user'").fetchone()[0],
        "comments": db.execute("SELECT COUNT(*) FROM comment").fetchone()[0],
        "recommendations": db.execute("SELECT COUNT(*) FROM recommendation").fetchone()[0],
    }
    users = db.execute(
        """
        SELECT u.id, u.username, u.role, u.create_time,
               COUNT(DISTINCT f.id) AS favorite_count,
               COUNT(DISTINCT c.id) AS comment_count,
               COUNT(DISTINCT h.id) AS history_count
        FROM app_user u
        LEFT JOIN favorite f ON f.user_id = u.id
        LEFT JOIN comment c ON c.user_id = u.id
        LEFT JOIN browsing_history h ON h.user_id = u.id
        GROUP BY u.id ORDER BY u.id DESC
        """
    ).fetchall()
    recent_comments = db.execute(
        """
        SELECT c.id, c.content, c.create_time, u.username, s.name AS spot_name
        FROM comment c
        JOIN app_user u ON u.id = c.user_id
        JOIN scenic_spot s ON s.id = c.spot_id
        ORDER BY c.id DESC LIMIT 20
        """
    ).fetchall()
    recent_preferences = db.execute(
        "SELECT * FROM user_preference ORDER BY id DESC LIMIT 10"
    ).fetchall()
    return render_template(
        "admin.html",
        spots=spots,
        stats=stats,
        users=users,
        recent_comments=recent_comments,
        recent_preferences=recent_preferences,
        **option_context(),
    )


@app.post("/admin/add")
@admin_required
def admin_add():
    values = spot_values(request.form)
    if not values["name"] or not values["city"]:
        flash("景点名称和城市不能为空。", "error")
    else:
        db = get_db()
        db.execute(
            """
            INSERT INTO scenic_spot
            (name, province, city, season, style_type, budget_level,
             play_days, suitable_people, introduction)
            VALUES (:name, :province, :city, :season, :style_type, :budget_level,
                    :play_days, :suitable_people, :introduction)
            """,
            values,
        )
        db.commit()
        flash("景点新增成功。", "success")
    return redirect(url_for("admin"))


@app.post("/admin/edit/<int:spot_id>")
@admin_required
def admin_edit(spot_id):
    values = spot_values(request.form)
    values["id"] = spot_id
    db = get_db()
    db.execute(
        """
        UPDATE scenic_spot SET
        name=:name, province=:province, city=:city, season=:season,
        style_type=:style_type, budget_level=:budget_level, play_days=:play_days,
        suitable_people=:suitable_people, introduction=:introduction
        WHERE id=:id
        """,
        values,
    )
    db.commit()
    flash("景点信息已更新。", "success")
    return redirect(url_for("admin"))


@app.post("/admin/delete/<int:spot_id>")
@admin_required
def admin_delete(spot_id):
    db = get_db()
    db.execute("DELETE FROM scenic_spot WHERE id = ?", (spot_id,))
    db.commit()
    flash("景点已删除。", "success")
    return redirect(url_for("admin"))


@app.post("/admin/comment/<int:comment_id>/delete")
@admin_required
def admin_delete_comment(comment_id):
    db = get_db()
    db.execute("DELETE FROM comment WHERE id = ?", (comment_id,))
    db.commit()
    flash("评论已由管理员删除。", "success")
    return redirect(url_for("admin"))


@app.route("/assets/<path:filename>")
def assets(filename):
    """复用文件夹 1 中现有的风景图片。"""
    if filename not in {"picture1.jpg", "photo1.jpg", "photo2.png", "photo3.png", "photo4.png"}:
        return "Not found", 404
    return send_from_directory(BASE_DIR, filename)


def option_context():
    return {"seasons": SEASONS, "styles": STYLES, "budgets": BUDGETS, "days": DAYS, "people": PEOPLE}


def spot_values(form):
    fields = [
        "name", "province", "city", "season", "style_type", "budget_level",
        "play_days", "suitable_people", "introduction",
    ]
    return {field: form.get(field, "").strip() for field in fields}


@app.context_processor
def template_helpers():
    return {"split_tags": split_tags, "current_user": g.user}


if not Path(app.config["DATABASE"]).exists():
    init_database(app.config["DATABASE"])


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=os.getenv("FLASK_DEBUG") == "1")
