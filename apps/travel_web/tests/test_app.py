import tempfile
import unittest
from pathlib import Path

from app import app, calculate_match_score, generate_recommend_reason
from init_db import init_database


class TravelSystemTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        init_database(self.db_path)
        app.config.update(TESTING=True, DATABASE=str(self.db_path))
        self.client = app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def admin_login(self):
        return self.client.post(
            "/login",
            data={"username": "admin", "password": "admin123"},
            follow_redirects=True,
        )

    def test_home_and_admin_pages(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/admin").status_code, 302)
        self.admin_login()
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)
        self.assertIn("乌镇", response.get_data(as_text=True))

    def test_score_weights_and_recommend_reason(self):
        preference = {
            "season": "春季", "style_type": "小桥流水",
            "budget_level": "中等预算", "play_days": "2-3天",
            "people_type": "情侣",
        }
        spot = {
            "name": "乌镇", "season": "春季,秋季", "style_type": "小桥流水,古韵文化",
            "budget_level": "中等预算", "play_days": "2-3天", "suitable_people": "情侣,家庭",
        }
        score, details, _, _ = calculate_match_score(preference, spot)
        # 未提供出发地距离时 origin 维度为 0，各偏好维度全中的最高分为 85。
        self.assertEqual(score, 85)
        self.assertEqual(details["season"], 25)
        self.assertIn("匹配度为 85.0%", generate_recommend_reason(preference, spot, score))

    def test_recommendation_is_sorted_and_saved(self):
        response = self.client.post(
            "/recommend",
            data={
                "season": "春季", "style_type": "小桥流水",
                "budget_level": "中等预算", "play_days": "2-3天",
                "people_type": "情侣",
            },
        )
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        # 两阶段推荐：/recommend 先返回城市列表，偏好已保存并透传。
        self.assertIn("嘉兴", html)
        self.assertIn("88", html)
        self.assertIn("preference_id=", html)
        self.assertLess(html.index("嘉兴"), html.index("上饶"))

    def test_admin_crud(self):
        self.admin_login()
        add = self.client.post(
            "/admin/add",
            data={
                "name": "测试景点", "province": "测试省", "city": "测试市",
                "season": "春季", "style_type": "山水自然",
                "budget_level": "低预算", "play_days": "1天",
                "suitable_people": "个人", "introduction": "测试简介",
            },
            follow_redirects=True,
        )
        self.assertIn("测试景点", add.get_data(as_text=True))

    def register_and_login(self):
        return self.client.post(
            "/register",
            data={"username": "traveler", "password": "secret123", "confirm_password": "secret123"},
            follow_redirects=True,
        )

    def test_register_login_and_profile(self):
        response = self.register_and_login()
        self.assertEqual(response.status_code, 200)
        self.assertIn("个人中心", response.get_data(as_text=True))
        self.client.get("/logout")
        login = self.client.post(
            "/login",
            data={"username": "traveler", "password": "secret123"},
            follow_redirects=True,
        )
        self.assertIn("traveler", login.get_data(as_text=True))

    def test_history_favorite_and_comment(self):
        self.register_and_login()
        self.client.get("/detail/1")
        favorite = self.client.post("/favorite/1", follow_redirects=True)
        self.assertIn("已收藏", favorite.get_data(as_text=True))
        comment = self.client.post(
            "/detail/1/comment",
            data={"content": "春天的水乡氛围很适合慢慢游览。"},
            follow_redirects=True,
        )
        self.assertIn("春天的水乡氛围", comment.get_data(as_text=True))
        profile = self.client.get("/profile").get_data(as_text=True)
        self.assertIn("乌镇", profile)
        self.assertIn("春天的水乡氛围", profile)

    def test_profile_requires_login(self):
        response = self.client.get("/profile")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_normal_user_cannot_access_admin(self):
        self.register_and_login()
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin", response.headers["Location"])

    def test_admin_login_opens_dashboard_with_private_data(self):
        self.register_and_login()
        self.client.get("/logout")
        response = self.client.post(
            "/login",
            data={"username": "admin", "password": "admin123"},
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("管理后台", html)
        self.assertIn("用户数据", html)
        self.assertIn("traveler", html)

    def test_anonymous_user_cannot_modify_spots(self):
        response = self.client.post("/admin/delete/1")
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            app.config["DATABASE"] = str(self.db_path)
            from app import get_db
            self.assertIsNotNone(
                get_db().execute("SELECT id FROM scenic_spot WHERE id = 1").fetchone()
            )


if __name__ == "__main__":
    unittest.main()
