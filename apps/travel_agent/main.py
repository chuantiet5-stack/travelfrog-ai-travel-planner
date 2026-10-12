"""
NanoClaw 入口文件

提供命令行交互界面，组装 Agent 各组件并启动对话循环。

使用方法：
    python main.py

命令：
    /exit   - 退出程序
    /clear  - 清空对话历史
    /tools  - 查看可用工具列表
"""

import asyncio
import os
import sys

from config import load_config
from providers.openai_compat import OpenAICompatProvider
from agent.tools.registry import ToolRegistry
from agent.tools.filesystem import ReadFileTool, WriteFileTool, ListDirTool
from agent.tools.shell import ExecTool
from agent.tools.web_fetch import WebFetchTool
from agent.tools.web_search import WebSearchTool
from agent.tools.recommendation_api import RecommendationAPITool
from agent.tools.spawn import SpawnSubagentTool
from agent.tools.food import FoodFilterTool
from agent.tools.mcp_server import MCPClientManager
from agent.skills import SkillsLoader
from agent.context import ContextBuilder
from agent.loop import AgentLoop
from session.manager import SessionManager
from agent.memory import MemoryConsolidator
from bus.queue import MessageBus
from channels.cli import CLIChannel
from channels.feishu import FeishuChannel
from channels.qq import QQChannel
from channels.web import WebChannel
from gateway import Gateway


def build_agent(config, session_key: str, mcp_manager: MCPClientManager = None) -> AgentLoop:
    """
    组装 Agent 实例
    Args:
        config: 配置对象（由 load_config() 返回）
        session_key: 会话标识，格式为 "{channel}:{sender_id}"
        mcp_manager: MCP 客户端管理器（可选）
    加载配置、创建各组件并组装 AgentLoop：
    1. 加载配置文件
    2. 验证 API 密钥
    3. 创建 LLM Provider
    4. 注册文件系统工具
    5. 注册 MCP 工具（如果有）
    6. 创建上下文构建器
    7. 组装 AgentLoop

    Returns:
        AgentLoop: 组装完成的 Agent 实例
    """
    # 加载配置
    config = load_config()

    # 验证 API 密钥
    if not config.api_key:
        print("错误: 未配置 API 密钥")
        print("请在 config.json 中设置 api_key，或设置环境变量 NANOCLAW_API_KEY")
        sys.exit(1)

    # 创建 LLM Provider
    provider = OpenAICompatProvider(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
    )

    # ===============================
    # 创建工具注册表
    # ===============================

    tools = ToolRegistry()

    is_travel_agent = (session_key.startswith("travel:") or session_key.startswith("cli:"))


    if is_travel_agent:

        # ===============================
        # 旅游 Agent 专用工具
        # ===============================

        # 必须保留：
        # 用于读取 skills/trip_planner/SKILL.md
        tools.register(ReadFileTool(config.workspace))

        # 旅游规划允许进行网络查询
        tools.register(WebSearchTool())
        tools.register(WebFetchTool())
        tools.register(RecommendationAPITool())
        tools.register(FoodFilterTool())
        print(
            "当前工具:",
            tools.list_tools()
        )
        print(
            f"[{session_key}] 已启用旅游 Agent 专用工具集"
        )

    else:

        # ===============================
        # 普通 Agent 完整工具集
        # ===============================

        tools.register(ReadFileTool(config.workspace))
        tools.register(WriteFileTool(config.workspace))
        tools.register(ListDirTool(config.workspace))
        tools.register(ExecTool(config.workspace))

        tools.register(WebSearchTool())
        tools.register(WebFetchTool())

        # 注册子 Agent 工具
    def create_provider(model=None):
        """Provider 工厂函数，子 Agent 用。"""
        # 子 Agent 默认用 subagent 模型（更便宜）
        if model is None and config.models:
            model = config.models.get("subagent", config.model)
        return OpenAICompatProvider(
            api_key=config.api_key,
            base_url=config.base_url,
            model=model or config.model
        )

    if not is_travel_agent:
        tools.register(
            SpawnSubagentTool(
                provider_factory=create_provider,
                tools_registry=tools,
                workspace=config.workspace,
            )
        )

    # 注册 MCP 工具（如果有）
    if mcp_manager:
        mcp_tools = mcp_manager.get_tools()

        if session_key.startswith("travel:"):
            # 旅游 Agent 只允许使用旅游相关 MCP 工具
            travel_keywords = (
                "amap__",
                "seniverse__",
            )

            mcp_tools = [
                tool
                for tool in mcp_tools
                if tool.name.startswith(travel_keywords)
            ]

        for mcp_tool in mcp_tools:
            tools.register(mcp_tool)

        print(
            f"[{session_key}] 已注册 MCP 工具: "
            f"{len(mcp_tools)} 个"
        )

    # ===============================
    # 加载技能
    # ===============================

    skills_loader = SkillsLoader(
        skills_dir=os.path.join(config.workspace, "skills")
    )

    # 所有技能摘要
    skills_summary = skills_loader.build_skills_summary()

    # ===============================
    # 根据渠道加载专属技能
    # ===============================

    skill_content = ""


    # 旅游 Agent 自动加载旅游规划技能
    if session_key.startswith("travel:"):

        skill_content = (
            skills_loader.load_skill("trip_planner")
            or ""
        )

        if skill_content:
            print(
                f"[{session_key}] 已加载旅游规划技能: trip_planner"
            )


    # 打印技能数量
    if skills_summary:

        skills_list = skills_loader.list_skills()

        print(
            f"{session_key} 已发现技能: {len(skills_list)} 个"
        )

    # 创建会话管理器
    session_manager = SessionManager(
        sessions_dir=os.path.join(config.workspace, "workspace", "sessions")
    )

    # session_key = "cli:direct"
    # 如果有历史，显示恢复提示
    existing_history = session_manager.get_history(session_key)
    if existing_history:
        print(f"[{session_key}] 已恢复 {len(existing_history)} 条历史消息")

    # 打印已注册的工具
    print(f"[{session_key}] 已注册工具：{tools.list_tools()}")

    # 创建上下文构建器
    context = ContextBuilder(
        workspace=config.workspace,
        identity_file=config.identity_file,
        skills_summary=skills_summary,
        skill_content=skill_content,
    )

    # 创建 Token 压缩器
    consolidator = MemoryConsolidator(
        provider=provider,
        workspace=config.workspace,
        token_budget=32000
    )

    # 组装 AgentLoop
    agent = AgentLoop(
        provider=provider,
        tools=tools,
        context=context,
        session_manager=session_manager,
        model=config.model,
        max_iterations=config.max_iterations,
        # session_key="cli:direct",
        session_key=session_key,
    )

    agent.consolidator = consolidator  # 挂载压缩器

    return agent


async def interactive_loop(agent: AgentLoop) -> None:
    """
    交互式对话循环

    读取用户输入，调用 Agent 处理并打印响应。
    支持命令：/exit、/clear、/tools

    Args:
        agent: AgentLoop 实例
    """
    print("\n开始对话（输入 /exit 退出）")

    while True:
        try:
            # 读取用户输入
            user_input = input("\n你: ").strip()

            # 空输入跳过
            if not user_input:
                continue

            # 处理命令
            if user_input == "/exit":
                print("再见！")
                break

            if user_input == "/clear":
                agent.clear_history()
                print("对话历史已清空")
                continue

            if user_input == "/tools":
                tools = agent.tools.list_tools()
                print(f"可用工具: {', '.join(tools)}")
                continue

            # 调用 Agent 处理
            print("\nNanoClaw: ", end="", flush=True)
            response = await agent.run(user_input)
            print(response)

        except KeyboardInterrupt:
            # Ctrl+C 优雅退出
            print("\n\n再见！")
            break

        except EOFError:
            # 输入结束（如管道输入完毕）
            print("\n再见！")
            break


# 新版：通过 Gateway 启动
async def async_main() -> None:
    """
    异步主入口

    启动 MCP Server、组装 Agent、启动 Gateway。
    """
    # 启动 banner
    print("=" * 50)
    print("  NanoClaw - 智能代码助手")
    print("  模型: Kimi-K2.5 (硅基流动)")
    print("=" * 50)
    #加载配置文件
    config = load_config()
    bus = MessageBus()

    # 启动 MCP Server（如果有配置）
    mcp_manager = None
    if config.mcp_servers:
        mcp_manager = MCPClientManager(config.mcp_servers)
        await mcp_manager.connect_all(timeout=30)
        # await mcp_manager.connect_all(timeout=30.0)

    # 定义 Agent 工厂函数
    def create_agent(session_key: str) -> AgentLoop:
        return build_agent(config, session_key, mcp_manager)

    # 注册渠道
    cli_channel = CLIChannel(bus)
    channels = [cli_channel]

    # 飞书渠道（如果配置了 feishu app_id / app_secret 就自动启用）
    if config.feishu_app_id and config.feishu_app_secret:
        feishu_channel = FeishuChannel(bus, config.feishu_app_id, config.feishu_app_secret)
        channels.append(feishu_channel)
        print("[启动] 已启用飞书渠道")
    else:
        print("[启动] 未配置飞书，跳过飞书渠道")

    # QQ 渠道（如果配置了 qq app_id / app_secret 就自动启用）
    if config.qq_app_id and config.qq_app_secret:
        qq_channel = QQChannel(bus, config.qq_app_id, config.qq_app_secret)
        channels.append(qq_channel)
        print("[启动] 已启用 QQ 渠道")
    else:
        print("[启动] 未配置 QQ，跳过 QQ 渠道")

    # Web 渠道（默认启用，不需要外部凭证）
    if config.web_enabled:
        web_channel = WebChannel(
            bus,
            host=config.web_host,
            port=config.web_port,
            agent_factory=create_agent,
)
        channels.append(web_channel)
        print(f"[启动] 已启用 Web 渠道: http://{config.web_host}:{config.web_port}")
    else:
        print("[启动] Web 渠道已禁用")

    # 启动网关
    gateway = Gateway(bus, channels, create_agent)

    # 预创建 CLI Agent，让初始化信息在启动时就显示
    cli_session_key = "cli:local"
    agent = create_agent(cli_session_key)
    gateway._agents[cli_session_key] = agent

    # 注入工具列表和清空回调给 CLI 渠道
    cli_channel.tool_names = agent.tools.list_tools()
    cli_channel._clear_callback = lambda: agent.clear_history()

    try:
        await gateway.run()
    except KeyboardInterrupt:
        print("\n[NanoClaw] 正在退出...")
    finally:
        # 清理 MCP 连接
        if mcp_manager:
            await mcp_manager.shutdown()


def main() -> None:
    """
    主入口（同步包装）

    打印启动 banner，组装 Agent 并启动交互循环。
    """
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n[NanoClaw] 正在退出...")
        import os
        os._exit(0)  # 强制退出，杀掉残留的 WebSocket 子线程


if __name__ == "__main__":
    main()