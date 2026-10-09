"""
出发地 / 交通便利度相似度计算。
"""


def origin_similarity(distance_km, max_distance_km=2500):
    """
    根据出发地与目的地之间的距离，
    计算交通便利度相似度。

    返回值范围：0~1

    距离越近，相似度越高。
    距离越远，相似度越低。
    """

    if distance_km is None:
        return 0.0

    try:
        distance_km = float(distance_km)
    except (TypeError, ValueError):
        return 0.0

    if distance_km < 0:
        return 0.0

    if distance_km >= max_distance_km:
        return 0.0

    return round(
        1 - distance_km / max_distance_km,
        4,
    )