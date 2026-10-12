from recommendation.similarity import (
    exact_similarity,
    ordered_similarity,
    multi_label_similarity
)


print("=== 多标签风格测试 ===")

print(
    "单标签完全匹配:",
    multi_label_similarity(
        "古韵文化",
        "古韵文化,摄影人文"
    )
)

print(
    "单标签不匹配:",
    multi_label_similarity(
        "古韵文化",
        "山水自然,摄影人文"
    )
)

print(
    "用户两个标签，全部命中:",
    multi_label_similarity(
        "古韵文化,山水自然",
        "古韵文化,摄影人文,山水自然"
    )
)

print(
    "用户两个标签，命中一个:",
    multi_label_similarity(
        "古韵文化,山水自然",
        "古韵文化,摄影人文"
    )
)

print(
    "用户两个标签，一个都没命中:",
    multi_label_similarity(
        "古韵文化,山水自然",
        "海滨休闲,摄影人文"
    )
)

print(
    "中文逗号:",
    multi_label_similarity(
        "古韵文化，山水自然",
        "古韵文化，摄影人文，山水自然"
    )
)

print(
    "中文顿号:",
    multi_label_similarity(
        "古韵文化、山水自然",
        "古韵文化、摄影人文、山水自然"
    )
)


print("\n=== 12种旅游风格测试 ===")

styles = [
    "古韵文化",
    "小桥流水",
    "山水自然",
    "海滨休闲",
    "城市烟火",
    "摄影人文",
    "雪山度假",
    "亲子乐园",
    "温泉康养",
    "极限户外",
    "沙漠戈壁",
    "草原牧歌"
]

for style in styles:
    score = multi_label_similarity(
        style,
        style
    )
    print(f"{style}: {score}")