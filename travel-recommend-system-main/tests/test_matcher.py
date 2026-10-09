from recommendation.matcher import calculate_match_score


# =========================================================
# 测试用户需求
# =========================================================

user_pref = {
    "season": "秋季",
    "style_type": "古韵文化,小桥流水",
    "budget_level": "中等预算",
    "play_days": "2-3天",
    "people_type": "情侣",

    # 五个维度优先级
    "priority": {
        "season": 3,
        "style_type": 5,
        "budget_level": 3,
        "play_days": 2,
        "people_type": 4,
    },
}


# =========================================================
# 测试景点
# =========================================================

spot = {
    "name": "测试景点",

    # 完全匹配
    "season": "春季,秋季",

    # 两个用户风格只命中一个
    "style_type": "古韵文化,摄影人文",

    # 完全匹配
    "budget_level": "中等预算,高预算",

    # 完全匹配
    "play_days": "1天,2-3天",

    # 不匹配
    "suitable_people": "家庭,个人",
}


# =========================================================
# 计算匹配
# =========================================================

score, details, similarities, weights = calculate_match_score(
    user_pref,
    spot,
)


# =========================================================
# 输出结果
# =========================================================

print("========== 基础匹配测试 ==========")

print(f"景点：{spot['name']}")

print("\n--- 相似度 ---")

for key, value in similarities.items():
    print(f"{key}: {value}")


print("\n--- 动态权重 ---")

for key, value in weights.items():
    print(f"{key}: {value}")


print("\n--- 各维度贡献 ---")

for key, value in details.items():
    print(f"{key}: {value}")


print("\n--- 最终基础匹配分 ---")

print(f"{score}")