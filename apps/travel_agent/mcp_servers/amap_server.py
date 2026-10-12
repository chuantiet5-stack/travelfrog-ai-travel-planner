# mcp_servers/amap_server.py
"""
高德地图 MCP Server
提供景点搜索、POI查询、地理编码等功能
"""

import json
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent

# 从配置文件读取 API Key（直接读原始 JSON，因为 NanoClawConfig 没有 amap 字段）
import sys
import os
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

AMAP_KEY = ""
_config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
if os.path.isfile(_config_path):
    try:
        with open(_config_path, "r", encoding="utf-8") as _f:
            _data = json.load(_f)
        AMAP_KEY = _data.get("amap", {}).get("api_key", "")
    except Exception:
        pass

# 创建 MCP Server
mcp = FastMCP("amap-server")

@mcp.tool()
async def geocode_city(city: str) -> str:
    """将城市名称转换为经纬度。

    Args:
        city: 城市名称，例如“广州”“杭州”“成都”

    Returns:
        城市对应的经纬度信息
    """

    async with httpx.AsyncClient(timeout=30.0) as client:
        url = "https://restapi.amap.com/v3/geocode/geo"

        params = {
            "key": AMAP_KEY,
            "address": city,
            "output": "JSON",
        }

        response = await client.get(
            url,
            params=params,
        )

        data = response.json()

        if data.get("status") != "1":
            return json.dumps(
                {
                    "success": False,
                    "city": city,
                    "message": data.get(
                        "info",
                        "地理编码失败",
                    ),
                },
                ensure_ascii=False,
            )

        geocodes = data.get("geocodes", [])

        if not geocodes:
            return json.dumps(
                {
                    "success": False,
                    "city": city,
                    "message": "未找到该城市的地理位置",
                },
                ensure_ascii=False,
            )

        location = geocodes[0].get(
            "location",
            "",
        )

        return json.dumps(
            {
                "success": True,
                "city": city,
                "location": location,
                "formatted_address": geocodes[0].get(
                    "formatted_address",
                    "",
                ),
                "province": geocodes[0].get(
                    "province",
                    "",
                ),
                "citycode": geocodes[0].get(
                    "citycode",
                    "",
                ),
                "adcode": geocodes[0].get(
                    "adcode",
                    "",
                ),
            },
            ensure_ascii=False,
            indent=2,
        )


@mcp.tool()
async def route_distance(
    origin: str,
    destination: str,
    distance_type: int = 1,
) -> str:
    """计算两个坐标之间的距离和预计时间。

    Args:
        origin: 起点经纬度，例如“113.264385,23.129112”
        destination: 终点经纬度，例如“120.153576,30.287459”
        distance_type:
            0 = 直线距离
            1 = 驾车距离

    Returns:
        距离（米）、距离（公里）和预计时间（秒）
    """

    async with httpx.AsyncClient(timeout=30.0) as client:
        url = "https://restapi.amap.com/v3/distance"

        params = {
            "key": AMAP_KEY,
            "origins": origin,
            "destination": destination,
            "type": distance_type,
            "output": "JSON",
        }

        response = await client.get(
            url,
            params=params,
        )

        data = response.json()

        if data.get("status") != "1":
            return json.dumps(
                {
                    "success": False,
                    "origin": origin,
                    "destination": destination,
                    "message": data.get(
                        "info",
                        "距离计算失败",
                    ),
                },
                ensure_ascii=False,
            )

        results = data.get("results", [])

        if not results:
            return json.dumps(
                {
                    "success": False,
                    "origin": origin,
                    "destination": destination,
                    "message": "没有获得路线距离结果",
                },
                ensure_ascii=False,
            )

        result = results[0]

        try:
            distance_m = float(
                result.get("distance", 0)
            )
        except (TypeError, ValueError):
            distance_m = 0.0

        try:
            duration_s = float(
                result.get("duration", 0)
            )
        except (TypeError, ValueError):
            duration_s = 0.0

        return json.dumps(
            {
                "success": True,
                "origin": origin,
                "destination": destination,
                "distance_m": round(distance_m, 2),
                "distance_km": round(
                    distance_m / 1000,
                    2,
                ),
                "duration_s": round(
                    duration_s,
                    2,
                ),
                "duration_min": round(
                    duration_s / 60,
                    2,
                ),
            },
            ensure_ascii=False,
            indent=2,
        )


@mcp.tool()
async def search_poi(keywords: str, city: str, types: str = "风景名胜|旅游景点", offset: int = 10) -> str:
    """根据关键词和城市搜索景点/POI（兴趣点）

    Args:
        keywords: 搜索关键词，如'景点'、'博物馆'
        city: 城市名称，如'成都'
        types: POI类型，如'风景名胜|旅游景点'
        offset: 返回结果数量，默认10
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = "https://restapi.amap.com/v3/place/text"
        params = {
            "key": AMAP_KEY,
            "keywords": keywords,
            "city": city,
            "types": types,
            "offset": offset,
            "extensions": "all",
        }
        response = await client.get(url, params=params)
        data = response.json()
        if data.get("status") == "1":
            pois = data.get("pois", [])
            result = []
            for poi in pois[:10]:
                result.append({
                    "name": poi.get("name", ""),
                    "address": poi.get("address", ""),
                    "location": poi.get("location", ""),
                    "pname": poi.get("pname", ""),
                    "cityname": poi.get("cityname", ""),
                    "adname": poi.get("adname", ""),
                    "type": poi.get("type", ""),
                    "typecode": poi.get("typecode", ""),
                    "distance": poi.get("distance", ""),
                    "biz_type": poi.get("biz_type", ""),
                    "tel": poi.get("tel", ""),
                })
            return json.dumps(result, ensure_ascii=False, indent=2)
        else:
            return f"搜索失败: {data.get('info', '未知错误')}"

@mcp.tool()
async def search_around(location: str, keywords: str, radius: int = 3000) -> str:
    """在指定坐标周边搜索景点

    Args:
        location: 经纬度，格式'经度,纬度'
        keywords: 搜索关键词
        radius: 搜索半径（米），默认3000
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = "https://restapi.amap.com/v3/place/around"
        params = {
            "key": AMAP_KEY,
            "location": location,
            "keywords": keywords,
            "radius": radius,
            "extensions": "all",
        }
        response = await client.get(url, params=params)
        data = response.json()
        if data.get("status") == "1":
            pois = data.get("pois", [])
            result = []
            for poi in pois[:10]:
                result.append({
                    "name": poi.get("name", ""),
                    "address": poi.get("address", ""),
                    "location": poi.get("location", ""),
                    "distance": poi.get("distance", ""),
                })
            return json.dumps(result, ensure_ascii=False, indent=2)
        else:
            return f"搜索失败: {data.get('info', '未知错误')}"

@mcp.tool()
async def weather(city: str, extensions: str = "base") -> str:
    """查询城市天气（实时或预报）

    Args:
        city: 城市名称
        extensions: base=实时，all=预报，默认base
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = "https://restapi.amap.com/v3/weather/weatherInfo"
        params = {
            "key": AMAP_KEY,
            "city": city,
            "extensions": extensions,
        }
        response = await client.get(url, params=params)
        data = response.json()
        if data.get("status") == "1":
            if extensions == "all":
                forecasts = data.get("forecasts", [])
                return json.dumps(forecasts, ensure_ascii=False, indent=2)
            else:
                lives = data.get("lives", [])
                return json.dumps(lives, ensure_ascii=False, indent=2)
        else:
            return f"天气查询失败: {data.get('info', '未知错误')}"

if __name__ == "__main__":
    mcp.run()
