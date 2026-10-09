"""
旅游推荐动态权重模块。

根据用户的偏好强度，对基础匹配权重进行调整。

注意：
第一版采用规则方法，不依赖 LLM。
"""


# 原系统基础权重
BASE_WEIGHTS = {
    "season": 25,
    "style_type": 25,
    "budget_level": 15,
    "play_days": 10,
    "people_type": 10,
	"origin": 15,
}


def calculate_dynamic_weights(user_pref):
    """
    根据用户偏好计算动态权重。

    当前规则：

    1. 如果用户明确强调某个因素，则提高该因素权重。
    2. 其他因素相应降低。
    3. 最终所有权重总和保持 100。

    user_pref 中可以增加：

        priority = {
			"origin": 3,
            "season": 1,
            "style_type": 5,
            "budget_level": 3,
            "play_days": 2,
            "people_type": 1,
        }

    优先级范围：
        1~5

    1 = 不太重要
    5 = 非常重要
    """

    weights = BASE_WEIGHTS.copy()

    priority = user_pref.get("priority", {})

    if not priority:
        return weights

    # 根据优先级进行调整
    for key, value in priority.items():

        if key not in weights:
            continue

        try:
            value = float(value)
        except (TypeError, ValueError):
            continue

        # 限制到 1~5
        value = max(1, min(5, value))

        # 以 3 为普通重要程度
        adjustment = (value - 3) * 5

        weights[key] += adjustment

    # 防止出现负数
    for key in weights:
        weights[key] = max(1, weights[key])

    # 重新归一化到 100
    total = sum(weights.values())

    weights = {
        key: round(value / total * 100, 2)
        for key, value in weights.items()
    }

    # 修正浮点误差
    difference = round(100 - sum(weights.values()), 2)

    if difference != 0:
        weights["style_type"] = round(
            weights["style_type"] + difference,
            2,
        )

    return weights