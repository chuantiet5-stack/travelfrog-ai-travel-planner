import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(
        command="D:/anaconda3/envs/test_ai/python.exe",
        args=["mcp_servers/unsplash_server.py"],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("=== 工具列表 ===")
            for t in tools.tools:
                print(f"- {t.name}: {t.description}")
            print(f"\n共 {len(tools.tools)} 个工具")

            print("\n=== 测试调用 search_photos ===")
            result = await session.call_tool("search_photos", {"query": "chengdu", "per_page": 3})
            for c in result.content:
                print(c.text if hasattr(c, "text") else c)

asyncio.run(main())