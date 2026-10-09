# mcp_servers/unsplash_server.py
"""
景点图片 MCP Server
使用百度图片搜索，支持中文景点，无需 API Key
"""

import json
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

mcp = FastMCP("attraction-image-server")

BAIDU_IMAGE_URL = "https://image.baidu.com/search/acjson"

async def _baidu_search(query: str, per_page: int) -> list:
    """调用百度图片搜索接口"""
    per_page = min(max(per_page, 1), 10)
    params = {
        "tn": "resultjson_com",
        "word": query,
        "pn": 0,
        "rn": per_page,
        "ipn": "rj",
        "fp": "result",
        "queryWord": query,
        "cl": 2,
        "lm": -1,
        "st": -1,
        "face": 0,
        "istype": 2,
        "nc": 1,
        "ie": "utf-8",
        "oe": "utf-8",
        "ct": 201326592,
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        resp = await client.get(BAIDU_IMAGE_URL, params=params, headers=headers)
        data = resp.json()
    items = data.get("data", []) if isinstance(data, dict) else []
    return [it for it in items if isinstance(it, dict) and it.get("thumbURL")] or []

def _normalize(item: dict) -> dict:
    return {
        "id": str(item.get("id", item.get("di", ""))),
        "url": item.get("thumbURL", ""),
        "regular": item.get("middleURL", item.get("thumbURL", "")),
        "full": item.get("objURL", item.get("middleURL", "")),
        "description": item.get("fromPageTitle", item.get("title", "")),
        "photographer": item.get("fromURL", "百度图片"),
    }

@mcp.tool()
async def search_photos(query: str, per_page: int = 3) -> str:
    """根据关键词搜索景点图片（中文景点支持好）

    Args:
        query: 搜索关键词，如'成都 宽窄巷子'、'武侯祠'
        per_page: 返回图片数量，默认3，最大10
    """
    items = await _baidu_search(query, per_page)
    if not items:
        return json.dumps({"query": query, "error": "未找到图片"}, ensure_ascii=False, indent=2)
    results = [_normalize(it) for it in items[:per_page]]
    return json.dumps(results, ensure_ascii=False, indent=2)

@mcp.tool()
async def get_attraction_image(name: str, city: str = "") -> str:
    """获取单个景点的主要展示图片

    Args:
        name: 景点名称
        city: 所在城市（可选，用于提高搜索精度）
    """
    query = f"{city}{name}" if city else name
    items = await _baidu_search(query, 1)
    if not items:
        return json.dumps({"name": name, "error": "未找到图片"}, ensure_ascii=False, indent=2)
    photo = _normalize(items[0])
    photo["name"] = name
    return json.dumps(photo, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    mcp.run()
