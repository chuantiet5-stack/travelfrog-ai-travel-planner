"""
城市级旅游推荐算法。

职责：

用户偏好
    ↓
景点匹配
    ↓
按照城市聚合
    ↓
计算城市匹配度
    ↓
输出城市候选

城市评分由三个因素组成：

1. 最高景点匹配度 S_max     50%
2. 城市景点平均匹配度 S_avg  30%
3. 匹配覆盖率 S_coverage     20%

公式：

S_city =
    0.5 * S_max
    + 0.3 * S_avg
    + 0.2 * S_coverage

注意：
这里只负责基础城市推荐。
后续再交给旅蛙 Agent 进行智能重排序。
"""

from recommendation.matcher import calculate_match_score


def group_spots_by_city(spots):
    """
    按城市对景点进行分组。

    例如：

    扬州：
        瘦西湖
        个园
        何园

    苏州：
        苏州园林

    返回：

    {
        "扬州": [...],
        "苏州": [...]
    }
    """

    cities = {}

    for spot in spots:
        city = spot["city"]

        if not city:
            continue

        cities.setdefault(city, []).append(spot)

    return cities


def calculate_city_score(city_results):
    """
    根据城市内景点评分计算城市匹配度。

    参数：
        city_results:
            该城市所有景点的匹配结果

    返回：
        城市匹配分数
    """

    if not city_results:
        return 0.0

    scores = [
        float(item["score"])
        for item in city_results
    ]

    # 最高景点匹配度
    max_score = max(scores)

    # 城市所有景点平均匹配度
    avg_score = sum(scores) / len(scores)

    # 匹配覆盖率
    #
    # 这里暂时把 >= 70 分视为“较高匹配”
    matched_count = sum(
        1
        for score in scores
        if score >= 70
    )

    coverage = (
        matched_count / len(scores) * 100
    )

    # 城市综合分数
    city_score = (
        0.5 * max_score
        + 0.3 * avg_score
        + 0.2 * coverage
    )

    return round(city_score, 2)

def calculate_final_city_score(
    base_city_score,
    origin_score,
    origin_weight,
):
    """
    计算加入交通便利度后的城市最终评分。

    参数：
        base_city_score:
            原有城市基础匹配分，范围 0~100。

        origin_score:
            出发地与目的城市之间的交通便利度，
            范围 0~100。

        origin_weight:
            交通便利度权重，范围 0~100。

    返回：
        城市最终评分，范围 0~100。
    """

    try:
        base_city_score = float(base_city_score)
        origin_score = float(origin_score)
        origin_weight = float(origin_weight)
    except (TypeError, ValueError):
        return round(base_city_score, 2)

    origin_weight = max(
        0,
        min(100, origin_weight),
    )

    base_weight = 100 - origin_weight

    final_score = (
        base_weight / 100 * base_city_score
        + origin_weight / 100 * origin_score
    )

    return round(final_score, 2)

def recommend_cities(user_pref, spots, top_n=5, city_distances=None,):
    """
    根据用户偏好推荐城市。

    参数：

        user_pref:
            用户旅游偏好

        spots:
            scenic_spot 查询结果

        top_n:
            返回城市数量

    返回：

        [
            {
                "city": "扬州",
                "score": 90.5,
                "max_score": 95,
                "avg_score": 88,
                "coverage": 75,
                "spots": [...]
            }
        ]
    """

    if not spots:
        return []

    # 1. 按城市分组
    cities = group_spots_by_city(spots)

    city_results = []

    # 2. 逐城市计算景点匹配
    for city, city_spots in cities.items():

        spot_results = []

        distance_km = None

        if city_distances:
            distance_km = city_distances.get(city)

        for spot in city_spots:

            score, details, similarities, weights = (
                calculate_match_score(
                    user_pref,
                    spot,
                    distance_km=distance_km,
                )
            )

            spot_results.append(
                {
                    "spot": spot,
                    "score": score,
                    "details": details,
                    "similarities": similarities,
                    "weights": weights,
                }
            )

        # 3. 计算城市分数
        city_score = calculate_city_score(
            spot_results
        )

        scores = [
            item["score"]
            for item in spot_results
        ]

        max_score = max(scores)
        avg_score = sum(scores) / len(scores)

        matched_count = sum(
            1
            for score in scores
            if score >= 70
        )

        coverage = (
            matched_count
            / len(scores)
            * 100
        )

        city_results.append(
            {
                "city": city,
                "score": city_score,
                "max_score": round(max_score, 2),
                "avg_score": round(avg_score, 2),
                "coverage": round(coverage, 2),
                "spots": spot_results,
            }
        )

    # 4. 城市排序
    city_results.sort(
        key=lambda item: (
            -item["score"],
            -item["max_score"],
            item["city"],
        )
    )

    # 5. Top-N 城市
    try:
        top_n = int(top_n)
    except (TypeError, ValueError):
        top_n = 5

    top_n = max(1, top_n)

    return city_results[:top_n]