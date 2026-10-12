import asyncio
import json

from agent.tools.recommendation_api import RecommendationAPITool


async def main():
    tool = RecommendationAPITool()

    result = await tool.execute(
        origin="广州",
        season="秋季",
        style_type="小桥流水",
        budget_level="中等预算",
        play_days="2-3天",
        people_type="情侣",
    )

    data = json.loads(result)

    print("=" * 60)
    print("RecommendationAPITool 测试结果")
    print("=" * 60)

    print("success:", data.get("success"))
    print("origin:", data.get("origin"))

    print("\n候选城市：")

    for index, city in enumerate(data.get("cities", []), start=1):
        print(
            f"{index}. "
            f"{city['city']} "
            f"score={city['score']}"
        )


if __name__ == "__main__":
    asyncio.run(main())