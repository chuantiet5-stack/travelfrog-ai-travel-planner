"""
Gateway 网关模块

Gateway 是多渠道接入的核心网关，负责：
- 管理多个渠道适配器（Channel）
- 处理入站消息：从 MessageBus 消费 → 分发给对应的 Agent
- 分发出站消息：从 MessageBus 消费 → 发送给对应的渠道
- 缓存 Agent 实例（按 session_key）

使用示例：
    bus = MessageBus()
    cli_channel = CLIChannel(bus)

    def create_agent(session_key: str) -> AgentLoop:
        # 根据 session_key 创建 Agent
        ...

    gateway = Gateway(
        bus=bus,
        channels=[cli_channel],
        agent_factory=create_agent
    )

    # 启动网关
    asyncio.run(gateway.run())
"""

import asyncio
from typing import Callable

from bus.queue import MessageBus, InboundMessage, OutboundMessage
from channels.base import Channel
from agent.loop import AgentLoop


class Gateway:
    """
    网关核心类

    管理多渠道接入和消息路由。
    """

    def __init__(
        self,
        bus: MessageBus,
        channels: list[Channel],
        agent_factory: Callable[[str], AgentLoop],
    ) -> None:
        """
        Args:
            bus: 消息总线实例
            channels: 渠道适配器列表
            agent_factory: Agent 创建函数，输入 session_key，返回 AgentLoop 实例
        """
        self.bus = bus
        self.channels = channels
        self.agent_factory = agent_factory

        # 内部状态
        self._agents: dict[str, AgentLoop] = {}  # 按 session_key 缓存 Agent
        self._channel_map: dict[str, Channel] = {}  # 按渠道名索引渠道

        # 构建渠道映射表
        for channel in channels:
            self._channel_map[channel.name] = channel

    async def run(self) -> None:
        """
        启动网关

        用 asyncio.gather 并发启动：
        - 所有渠道的 start()
        - _process_inbound() 入站消费循环
        - _dispatch_outbound() 出站分发循环
        """
        # 构建任务列表
        tasks = []

        # 添加所有渠道的启动任务
        for channel in self.channels:
            tasks.append(channel.start())

        # 添加入站和出站处理循环
        tasks.append(self._process_inbound())
        tasks.append(self._dispatch_outbound())

        # 并发启动所有任务
        try:
            # 等待所有任务（通常会阻塞直到某个渠道退出）
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            # 取消所有未完成的任务
            for task in tasks:
                if not task.done():
                    task.cancel()
            # 等待任务取消完成（忽略 CancelledError）
            await asyncio.gather(*tasks, return_exceptions=True)
            # 关闭所有渠道
            await self.shutdown()

    async def _process_inbound(self) -> None:
        """
        处理入站消息循环

        while True 循环：
        - 从 bus.consume_inbound() 取消息
        - 构造 session_key = f"{msg.channel}:{msg.sender_id}"
        - 从 _agents 缓存获取 Agent，不存在则调用 agent_factory 创建
        - 调用 agent.run(msg.content)
        - 构造 OutboundMessage 发布到 bus.publish_outbound()
        - 用 try-except 包裹，Agent 出错时发送友好错误消息
        """
        while True:
            try:
                # 从消息总线消费入站消息
                inbound_msg = await self.bus.consume_inbound()

                # 构造 session_key
                session_key = f"{inbound_msg.channel}:{inbound_msg.sender_id}"

                # 从缓存获取 Agent，不存在则创建
                if session_key not in self._agents:
                    agent = self.agent_factory(session_key)
                    self._agents[session_key] = agent
                else:
                    agent = self._agents[session_key]

                # 调用 Agent 处理消息
                try:
                    response = await agent.run(inbound_msg.content)

                    # 构造出站消息，透传入站 raw（含 message_id/msg_type）供渠道回复用
                    reply_to = None
                    if inbound_msg.raw and inbound_msg.raw.get("message_id"):
                        reply_to = inbound_msg.raw["message_id"]

                    outbound_msg = OutboundMessage(
                        channel=inbound_msg.channel,
                        chat_id=inbound_msg.chat_id,
                        content=response,
                        reply_to=reply_to,
                    )
                    if inbound_msg.raw:
                        outbound_msg.raw = inbound_msg.raw  # 透传 msg_type 等

                    # 发布到出站队列
                    await self.bus.publish_outbound(outbound_msg)

                except Exception as e:
                    # Agent 出错，发送友好错误消息
                    error_reply_to = None
                    if inbound_msg.raw and inbound_msg.raw.get("message_id"):
                        error_reply_to = inbound_msg.raw["message_id"]
                    error_msg = OutboundMessage(
                        channel=inbound_msg.channel,
                        chat_id=inbound_msg.chat_id,
                        content=f"抱歉，处理消息时发生了错误。请稍后重试。",
                        reply_to=error_reply_to,
                    )
                    if inbound_msg.raw:
                        error_msg.raw = inbound_msg.raw
                    await self.bus.publish_outbound(error_msg)

                    # 打印错误日志（调试用）
                    print(f"警告: Agent 处理出错 - {e}")

            except asyncio.CancelledError:
                # 任务被取消，退出循环
                break

            except Exception as e:
                # 消费循环异常，打印日志并继续
                print(f"警告: 入站处理循环异常 - {e}")
                continue

    async def _dispatch_outbound(self) -> None:
        """
        分发出站消息循环

        while True 循环：
        - 从 bus.consume_outbound() 取回复
        - 根据 msg.channel 找到对应的 Channel
        - 调用 channel.send(msg)
        """
        while True:
            try:
                # 从消息总线消费出站消息
                outbound_msg = await self.bus.consume_outbound()

                # 查找对应的渠道
                channel = self._channel_map.get(outbound_msg.channel)

                if channel is None:
                    print(f"警告: 渠道 '{outbound_msg.channel}' 不存在，无法发送消息")
                    continue

                # 调用渠道发送消息
                try:
                    await channel.send(outbound_msg)

                except Exception as e:
                    # 渠道发送失败，打印日志
                    print(f"警告: 渠道 '{outbound_msg.channel}' 发送失败 - {e}")

            except asyncio.CancelledError:
                # 任务被取消，退出循环
                break

            except Exception as e:
                # 分发循环异常，打印日志并继续
                print(f"警告: 出站分发循环异常 - {e}")
                continue

    async def shutdown(self) -> None:
        """
        关闭网关

        - 遍历 channels 调用 stop()
        - 清空 _agents 缓存
        """
        # 停止所有渠道
        for channel in self.channels:
            try:
                await channel.stop()
            except Exception as e:
                print(f"警告: 渠道 '{channel.name}' 关闭失败 - {e}")

        # 清空 Agent 缓存
        self._agents.clear()