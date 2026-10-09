"""
旅游推荐基础匹配算法。

当前版本已经加入：

1. 连续相似度
2. 动态权重
3. 多标签匹配

当前职责：

用户需求
    ↓
基础匹配算法
    ↓
计算每个景点的基础匹配分数
    ↓
Top-N 候选

注意：
这里暂时不负责最终推荐。
后续会把 Top-N 交给旅蛙 Agent 进行智能重排序。
"""

from recommendation.similarity import (
    exact_similarity,
    multi_label_similarity,
    ordered_similarity,
)

from recommendation.weights import calculate_dynamic_weights
from recommendation.origin_similarity import origin_similarity


def split_tags(value):
    """
    将数据库中的多值标签转换成集合。

    例如：

        "古韵文化,小桥流水"

    转换为：

        {"古韵文化", "小桥流水"}
    """

    return {
        item.strip()
        for item in str(value or "")
        .replace("，", ",")
        .replace("、", ",")
        .split(",")
        if item.strip()
    }


def calculate_match_score(user_pref, spot, distance_km=None):
    """
    计算用户需求与景点之间的基础匹配分数。

    当前算法：

    ① 连续相似度
       预算、游玩天数不再简单使用 0/1 匹配。

    ② 动态权重
       根据用户 preference priority 调整不同维度的重要程度。

    ③ 多标签匹配
       旅行风格、人群等可以支持多个标签。

    返回：

        score：
            0~100 的基础匹配分数

        details：
            每个维度最终贡献的分数

        similarities：
            每个维度的原始相似度

        weights：
            本次计算实际使用的动态权重
    """

    # =========================================================
    # 1. 获取动态权重
    # =========================================================

    weights = calculate_dynamic_weights(user_pref)

    # =========================================================
    # 2. 计算各维度相似度
    # =========================================================

    similarities = {}

    # ---------------------------------------------------------
    # 季节
    # ---------------------------------------------------------

    similarities["season"] = exact_similarity(
        user_pref["season"],
        spot["season"],
    )

    # ---------------------------------------------------------
    # 旅行风格
    # ---------------------------------------------------------

    similarities["style_type"] = multi_label_similarity(
        user_pref["style_type"],
        split_tags(spot["style_type"]),
    )

    # ---------------------------------------------------------
    # 预算
    # ---------------------------------------------------------

    similarities["budget_level"] = ordered_similarity(
        user_pref["budget_level"],
        spot["budget_level"],
        [
            "低预算",
            "中等预算",
            "高预算",
        ],
    )

    # ---------------------------------------------------------
    # 游玩天数
    # ---------------------------------------------------------

    similarities["play_days"] = ordered_similarity(
        user_pref["play_days"],
        spot["play_days"],
        [
            "1天",
            "2-3天",
            "4-5天",
            "一周以上",
        ],
    )

    # ---------------------------------------------------------
    # 人群
    # ---------------------------------------------------------

    similarities["people_type"] = multi_label_similarity(
        user_pref["people_type"],
        split_tags(spot["suitable_people"]),
    )

    if distance_km is None:
        similarities["origin"] = 0.0
    else:
        similarities["origin"] = origin_similarity(distance_km)
    
    
    # =========================================================
    # 3. 根据动态权重计算各维度贡献
    # =========================================================

    details = {}

    for key in weights:

        details[key] = round(
            weights[key] * similarities.get(key, 0),
            2,
        )

    # =========================================================
    # 4. 计算最终基础匹配分
    # =========================================================

    score = round(
        sum(details.values()),
        2,
    )

    return score, details, similarities, weights