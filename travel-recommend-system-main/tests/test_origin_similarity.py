from recommendation.origin_similarity import origin_similarity


test_distances = [
    100,
    500,
    1000,
    1500,
    2000,
    2500,
]


for distance in test_distances:

    score = origin_similarity(distance)

    print(
        f"距离：{distance} km"
        f" → 交通便利度：{score}"
    )