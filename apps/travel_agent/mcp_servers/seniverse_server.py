# mcp_servers/seniverse_server.py
"""
心知天气 MCP Server
提供实时天气和天气预报查询
"""

import json
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SENIVERSE_KEY = ""
_config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
if os.path.isfile(_config_path):
    try:
        with open(_config_path, "r", encoding="utf-8") as _f:
            _data = json.load(_f)
        SENIVERSE_KEY = _data.get("seniverse", {}).get("api_key", "")
    except Exception:
        pass

mcp = FastMCP("seniverse-server")

@mcp.tool()
async def get_weather_now(city: str) -> str:
    """获取指定城市的实时天气

    Args:
        city: 城市名称，如'北京'、'成都'
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = "https://api.seniverse.com/v3/weather/now.json"
        params = {
            "key": SENIVERSE_KEY,
            "location": city,
            "language": "zh-Hans",
            "unit": "c",
        }
        response = await client.get(url, params=params)
        data = response.json()
        if "results" in data and len(data["results"]) > 0:
            result = data["results"][0]
            now = result.get("now", {})
            location = result.get("location", {})
            return json.dumps({
                "city": location.get("name", city),
                "temperature": now.get("temperature", ""),
                "weather": now.get("text", ""),
                "wind_direction": now.get("wind_direction", ""),
                "wind_speed": now.get("wind_speed", ""),
                "humidity": now.get("humidity", ""),
            }, ensure_ascii=False, indent=2)
        else:
            return f"天气查询失败: {data}"

@mcp.tool()
async def get_weather_forecast(city: str, days: int = 3) -> str:
    """获取指定城市未来3-5天的天气预报

    Args:
        city: 城市名称
        days: 预报天数，默认3，最大5
    """
    days = min(days, 5)
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = "https://api.seniverse.com/v3/weather/daily.json"
        params = {
            "key": SENIVERSE_KEY,
            "location": city,
            "language": "zh-Hans",
            "unit": "c",
            "days": days,
        }
        response = await client.get(url, params=params)
        data = response.json()
        if "results" in data and len(data["results"]) > 0:
            result = data["results"][0]
            daily = result.get("daily", [])
            location = result.get("location", {})
            forecast = []
            for day in daily:
                forecast.append({
                    "date": day.get("date", ""),
                    "day_weather": day.get("text_day", ""),
                    "night_weather": day.get("text_night", ""),
                    "high": day.get("high", ""),
                    "low": day.get("low", ""),
                    "humidity": day.get("humidity", ""),
                    "rainfall": day.get("precip", ""),
                })
            return json.dumps({
                "city": location.get("name", city),
                "forecast": forecast,
            }, ensure_ascii=False, indent=2)
        else:
            return f"天气预报查询失败: {data}"

if __name__ == "__main__":
    mcp.run()
