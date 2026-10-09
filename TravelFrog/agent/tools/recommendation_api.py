import json
import urllib.request
import urllib.error
from typing import Any

from .base import Tool


class RecommendationAPITool(Tool):
    """
    调用旅游推荐系统 API。

    TravelFrog 负责调用，
    travel-recommend-system-main 负责基础推荐和候选城市召回。
    """

    @property
    def name(self) -> str:
        return "travel_recommendation"

    @property
    def description(self) -> str:
        return (
            "根据用户的旅游偏好调用旅游推荐系统，"
            "返回Top-N候选城市。"
            "适用于用户不知道去哪里时的目的地推荐。"
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "origin": {
                    "type": "string",
                    "description": "用户出发城市，例如广州",
                },
                "season": {
                    "type": "string",
                    "description": "出游季节，例如秋季",
                },
                "style_type": {
                    "type": "string",
                    "description": "旅游风格，例如小桥流水",
                },
                "budget_level": {
                    "type": "string",
                    "description": "预算等级，例如低预算、中等预算、高预算",
                },
                "play_days": {
                    "type": "string",
                    "description": "游玩天数，例如2-3天",
                },
                "people_type": {
                    "type": "string",
                    "description": "出游人群，例如个人、情侣、朋友、家庭",
                },
                "priority": {
                    "type": "object",
                    "description": "各旅游偏好的重要程度，取值1-5",
                    "properties": {
                        "origin": {
                            "type": "string",
                            "description": "出发地重要程度，1-5",
                        },
                        "season": {
                            "type": "string",
                            "description": "季节重要程度，1-5",
                        },
                        "style_type": {
                            "type": "string",
                            "description": "旅游风格重要程度，1-5",
                        },
                        "budget_level": {
                            "type": "string",
                            "description": "预算重要程度，1-5",
                        },
                        "play_days": {
                            "type": "string",
                            "description": "游玩天数重要程度，1-5",
                        },
                        "people_type": {
                            "type": "string",
                            "description": "出游人群重要程度，1-5",
                        },
                    },
                },
                "city_distances": {
                    "type": "object",
                    "description": "出发城市到候选城市的距离，单位为公里",
                },
            },
            "required": [
                "origin",
                "season",
                "style_type",
                "budget_level",
                "play_days",
                "people_type",
            ],
        }

    async def execute(self, **kwargs: Any) -> str:
        url = "http://127.0.0.1:5001/api/recommend"

        data = {
            "origin": kwargs.get("origin", ""),
            "season": kwargs.get("season", ""),
            "style_type": kwargs.get("style_type", ""),
            "budget_level": kwargs.get("budget_level", ""),
            "play_days": kwargs.get("play_days", ""),
            "people_type": kwargs.get("people_type", ""),
            "priority": kwargs.get(
                "priority",
                {
                    "origin": "3",
                    "season": "3",
                    "style_type": "3",
                    "budget_level": "3",
                    "play_days": "3",
                    "people_type": "3",
                },
            ),
            "city_distances": kwargs.get(
                "city_distances",
                {},
            ),
        }

        body = json.dumps(
            data,
            ensure_ascii=False,
        ).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=30,
            ) as response:

                result = json.loads(
                    response.read().decode("utf-8")
                )

                return json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                )

        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode(
                "utf-8",
                errors="replace",
            )

            return json.dumps(
                {
                    "success": False,
                    "error": f"推荐 API HTTP {exc.code}",
                    "detail": error_body,
                },
                ensure_ascii=False,
                indent=2,
            )

        except Exception as exc:
            return json.dumps(
                {
                    "success": False,
                    "error": "无法连接旅游推荐系统。",
                    "detail": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )