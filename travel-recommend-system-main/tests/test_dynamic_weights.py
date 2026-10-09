from recommendation.weights import calculate_dynamic_weights


base_pref = {
    "origin": "广州",
    "season": "秋季",
    "style_type": "小桥流水",
    "budget_level": "中等预算",
    "play_days": "2-3天",
    "people_type": "情侣",
}


for origin_priority in [1, 3, 5]:

    pref = base_pref.copy()

    pref["priority"] = {
        "origin": origin_priority,
        "season": 3,
        "style_type": 3,
        "budget_level": 3,
        "play_days": 3,
        "people_type": 3,
    }

    weights = calculate_dynamic_weights(pref)

    print(f"\n【出发地优先级 = {origin_priority}】")

    for key, value in weights.items():
        print(f"{key}: {value}")

    print("权重总和:", sum(weights.values()))