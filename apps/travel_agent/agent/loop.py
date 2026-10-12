"""Agent 主循环模块"""

import json

from providers.base import LLMProvider, LLMResponse
from agent.tools.registry import ToolRegistry
from agent.context import ContextBuilder
from session.manager import SessionManager


class AgentLoop:
    """Agent 执行循环

    管理 LLM 与工具之间的交互循环，包含：
    - LLM 与 Tool 的多轮交互
    - 工具调用防爆检测
    - Session History 持久化
    - Travel Trip State 持久化
    """

    # 防爆阈值常量
    FUSE_THRESHOLD = 5
    WARNING_THRESHOLD = 3
    WINDOW_SIZE = 12

    MAX_TRAVEL_TOOL_CALLS = 20

    def __init__(
        self,
        provider: LLMProvider,
        tools: ToolRegistry,
        context: ContextBuilder,
        session_manager: SessionManager,
        model: str | None = None,
        max_iterations: int = 32,
        session_key: str = "cli:direct"
    ):
        """初始化 AgentLoop

        Args:
            provider:
                LLM 提供方实例

            tools:
                工具注册表

            context:
                上下文构建器

            session_manager:
                会话管理器

            model:
                模型名称

            max_iterations:
                最大迭代次数

            session_key:
                会话标识符
        """

        self.provider = provider
        self.tools = tools
        self.context = context
        self.session_manager = session_manager
        self.session_key = session_key
        self.model = model
        self.max_iterations = max_iterations

        # ==============================
        # 旅游规划状态
        # ==============================
        self.travel_collection_state = {
            "destination": None,
            "days": None,
            "travelers": None,
            "preferences": [],
            "poi": [],
            "weather": None,
            "food": [],
            "completed": {
                "poi": False,
                "weather": False,
                "food": False
            }
        }

        # ===============================
        # 旅游任务工具查询状态
        # ===============================

        self.travel_query_types = set()

        # 工具最大调用次数
        self.max_tool_calls = 8

        # 当前轮工具调用计数
        self.tool_call_count = 0

        # 整合压缩器
        self.consolidator = None

        # =====================================================
        # 内部状态
        # =====================================================

        # 工具调用历史
        self._tool_call_history: list[str] = []

        self._travel_tool_call_count = 0

        # -----------------------------------------------------
        # 恢复 Session History
        # -----------------------------------------------------

        self._session_history: list[dict] = (
            session_manager.get_history(session_key)
        )

        # -----------------------------------------------------
        # 恢复 Trip State
        #
        # 只有 travel:* 会话使用 trip_state
        # 普通 NanoClaw 会话保持原有逻辑
        # -----------------------------------------------------

        if self.session_key.startswith("travel:"):
            self.trip_state: dict = (
                session_manager.get_trip_state(session_key)
            )

            print(
                f"[{self.session_key}] "
                f"已恢复旅行状态: "
                f"{len(self.trip_state)} 个字段"
            )

            if self.trip_state:
                print(
                    f"[{self.session_key}] "
                    f"当前旅行状态: "
                    f"{json.dumps(self.trip_state, ensure_ascii=False)}"
                )
        else:
            self.trip_state = {}
            self.travel_collection_state = {
            "poi": False,
            "weather": False,
            "food": False
            }



    async def run(self, user_message: str) -> str:

        self.travel_query_types.clear()

        self.tool_call_count = 0



        """执行 Agent 主循环

        Args:
            user_message:
                用户输入消息

        Returns:
            str:
                Agent 最终响应
        """

        # =====================================================
        # 1. 构建当前旅行状态上下文
        # =====================================================
        # 新用户请求，重置旅游查询状态

        self.travel_query_types.clear()

        self.tool_call_count = 0

        # 重置旅行规划收集状态
        if self.session_key.startswith("travel:"):
            self.travel_collection_state = {
                "destination": None,
                "days": None,
                "people": None,
                "preferences": [],
                "spots": [],
                "weather": None,
                "foods": [],
                "completed": {
                    "poi": False,
                    "weather": False,
                    "food": False
                }
            }

        
        current_message = user_message

        if self.session_key.startswith("travel:"):

            trip_state_context = self._build_trip_state_context()

            current_message = (
                trip_state_context
                + "\n\n"
                + "【用户最新消息】\n"
                + user_message
            )

        # =====================================================
        # 2. 构建初始 messages
        # =====================================================

        messages = self.context.build_messages(
            history=self._session_history,
            current_message=current_message
        )

        # =====================================================
        # 3. 保存用户原始消息
        #
        # 注意：
        # 保存到 History 的仍然是用户真实输入，
        # 不保存我们额外拼接的 trip_state_context。
        # =====================================================

        user_msg = {
            "role": "user",
            "content": user_message
        }

        self.session_manager.save_message(
            self.session_key,
            user_msg
        )

        # =====================================================
        # 4. Agent 多轮执行
        # =====================================================

        for iteration in range(self.max_iterations):

            # -------------------------------------------------
            # Context 压缩
            # -------------------------------------------------

            if hasattr(self, "consolidator") and self.consolidator:
                messages = await self.consolidator.maybe_consolidate(
                    messages
                )

            # -------------------------------------------------
            # 调用 LLM
            # -------------------------------------------------

            print(
                f"  💭 思考中... "
                f"(第 {iteration + 1} 轮)",
                end="",
                flush=True
            )

            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model,
                tool_choice="auto"
               
            )

            # -------------------------------------------------
            # 调试信息
            # -------------------------------------------------

            print(
                f"  🔍 finish_reason: "
                f"{response.finish_reason}"
            )

            print(
                f"  🔍 has_tool_calls: "
                f"{response.has_tool_calls}"
            )

            print(
                f"  🔍 tool_calls数量: "
                f"{len(response.tool_calls)}"
            )

            if response.content:
                print(
                    f"  📝 模型内容: "
                    f"{response.content[:300]}"
                )

            print(" ✓")

            # -------------------------------------------------
            # reasoning_content
            # -------------------------------------------------

            if (
                response.tool_calls
                and response.tool_calls[0].reasoning_content
            ):

                reasoning = (
                    response.tool_calls[0].reasoning_content
                )

                preview = (
                    reasoning[:300] + "..."
                    if len(reasoning) > 300
                    else reasoning
                )

                print(
                    f"  🧠 思考过程:\n"
                    f"{preview}"
                )

            # =================================================
            # 5. 错误处理
            # =================================================

            if response.finish_reason == "error":

                return (
                    "抱歉，发生了错误，请稍后重试。"
                )

            # =================================================
            # 6. 工具调用
            # =================================================

            if response.has_tool_calls:

                # -------------------------------------------------
                # 构造 assistant tool_call 消息
                # -------------------------------------------------

                assistant_msg = (
                    self._build_assistant_message(
                        response
                    )
                )

                messages.append(
                    assistant_msg
                )

                self.session_manager.save_message(
                    self.session_key,
                    assistant_msg
                )

                # -------------------------------------------------
                # 执行工具
                # -------------------------------------------------

                for tc in response.tool_calls:

                    args_json = json.dumps(
                        tc.arguments,
                        ensure_ascii=False
                    )

                    print(
                        f"\n  🛠️  调用工具: "
                        f"{tc.name}"
                        f"({args_json})"
                    )

                    # ---------------------------------------------
                    # 防爆检测
                    # ---------------------------------------------

                    check_result = (
                        self._check_tool_loop(
                            tc.name,
                            args_json
                        )
                    )

                    # ---------------------------------------------
                    # 熔断
                    # ---------------------------------------------

                    if (
                        check_result
                        and "熔断" in check_result
                    ):

                        print(
                            f"  🚨 {check_result}"
                        )

                        return check_result

                    # ---------------------------------------------
                    # 警告
                    # ---------------------------------------------

                    elif (
                        check_result
                        and "警告" in check_result
                    ):

                        print(
                            f"  ⚠️  {check_result}"
                        )

                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": (
                                f"系统警告："
                                f"{check_result}"
                            )
                        }

                        messages.append(
                            tool_msg
                        )

                        self.session_manager.save_message(
                            self.session_key,
                            tool_msg
                        )

                    # ---------------------------------------------
                    # 正常执行工具
                    # ---------------------------------------------

                    else:
                        # ==============================
                        # 旅游 Agent 工具调用次数限制
                        # ==============================
                        if self.session_key.startswith("travel:"):
                            self._travel_tool_call_count += 1

                            print(
                                f"  🧰 旅游工具调用 "
                                f"{self._travel_tool_call_count}/"
                                f"{self.MAX_TRAVEL_TOOL_CALLS}"
                            )

                            # 超过最大工具调用次数
                            if self._travel_tool_call_count > self.MAX_TRAVEL_TOOL_CALLS:
                                print(
                                    f"  🚨 旅游 Agent 工具调用达到上限 "
                                    f"({self.MAX_TRAVEL_TOOL_CALLS} 次)，"
                                    f"停止继续调用工具。"
                                )

                                self._save_to_history(messages)

                                final_response = await self.provider.chat(
                                    messages=messages,
                                    tools=None,
                                    model=self.model,
                                    tool_choice="auto",
                                )

                                return (
                                    final_response.content
                                    or "旅行规划生成失败，请稍后重试。"
                                )

                        # 正常执行工具
                        result = await self.tools.execute(
                            tc.name,
                            tc.arguments
                        )

                        # ==============================
                        # 更新旅行信息收集状态
                        # ==============================

                        if self.session_key.startswith("travel:"):

                            if "search_poi" in tc.name:
                                self.travel_collection_state["poi"] = True

                            elif "weather" in tc.name:
                                self.travel_collection_state["weather"] = True

                            elif tc.name == "food_filter":
                                self.travel_collection_state["food"] = True

                        preview = (
                            result[:200] + "..."
                            if len(result) > 200
                            else result
                        )

                        print(
                            f"  ✅ 结果: "
                            f"{preview}"
                        )

                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result
                        }

                        messages.append(
                            tool_msg
                        )
                        if (
                            self.session_key.startswith("travel:")
                            and
                            all(
                                self.travel_collection_state.values()
                            )
                        ):

                            messages.append(
                                {
                                    "role":"system",
                                    "content":
                                    """
                        旅行规划所需基础数据已经收集完成。

                        已经获得：

                        ✓ 景点信息
                        ✓ 天气信息
                        ✓ 美食信息

                        现在禁止继续调用任何工具。

                        请直接生成最终旅行攻略。
                        """
                                }
                            )

                        self.session_manager.save_message(
                            self.session_key,
                            tool_msg
                        )

                # ---------------------------------------------
                # 回到下一轮 LLM
                # ---------------------------------------------

                continue

            # =================================================
            # 7. 没有工具调用
            # =================================================

            self._save_to_history(
                messages
            )

            # -------------------------------------------------
            # 保存最终 assistant 消息
            # -------------------------------------------------

            if response.content:

                assistant_final_msg = {
                    "role": "assistant",
                    "content": response.content
                }

                self.session_manager.save_message(
                    self.session_key,
                    assistant_final_msg
                )

            return response.content or ""

        # =====================================================
        # 8. 超过最大迭代次数
        # =====================================================

        return (
            "已达到最大迭代次数，"
            "任务未完成。"
        )

    # =========================================================
    # Trip State
    # =========================================================

    def _build_trip_state_context(self) -> str:
        """构建当前旅行状态上下文。

        旅行 Agent 每次调用 LLM 时都会看到当前 trip_state。

        注意：
        trip_state 是“当前旅行的结构化状态”，
        不等同于完整聊天历史。
        """

        if not self.trip_state:

            return """
【当前旅行状态】

当前还没有保存的旅行状态。

请根据：
1. 用户最新消息
2. Session History
3. 旅游规划 Skill

理解当前旅行需求。

如果用户已经提供了目的地、天数、预算、
同行人群、旅行风格、旅行节奏等信息，
不要因为 trip_state 为空而认为信息缺失。
"""

        return f"""
【当前旅行状态】

以下是当前这趟旅行已经保存的结构化状态：

{json.dumps(
    self.trip_state,
    ensure_ascii=False,
    indent=2
)}

请将其作为当前旅行的重要上下文。

规则：

1. 当前状态中的信息可以帮助你理解用户需求。
2. 用户最新消息优先级高于旧的旅行状态。
3. 如果用户提出新的、更明确的信息，
   应以用户最新表达为准。
4. 不要因为 trip_state 中没有某个字段，
   就认为用户没有提供该信息。
5. 需要修改旅行状态时，应根据用户最新需求进行更新。
"""

    # =========================================================
    # Assistant Message
    # =========================================================

    def _build_assistant_message(
        self,
        response: LLMResponse
    ) -> dict:
        """构建 assistant 消息（含 tool_calls）"""

        assistant_msg: dict = {
            "role": "assistant",
            "content": response.content
        }

        # -----------------------------------------------------
        # tool_calls
        # -----------------------------------------------------

        tool_calls = []

        for tc in response.tool_calls:

            tool_call_item = {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(
                        tc.arguments,
                        ensure_ascii=False
                    )
                }
            }

            tool_calls.append(
                tool_call_item
            )

        if tool_calls:

            assistant_msg["tool_calls"] = (
                tool_calls
            )

        # -----------------------------------------------------
        # reasoning_content
        # -----------------------------------------------------

        if (
            response.tool_calls
            and response.tool_calls[0].reasoning_content
        ):

            assistant_msg[
                "reasoning_content"
            ] = (
                response.tool_calls[0]
                .reasoning_content
            )

        return assistant_msg

    # =========================================================
    # 防爆检测
    # =========================================================

    def _check_tool_loop(
        self,
        tool_name: str,
        tool_args_json: str
    ) -> str | None:
        """防爆检测

        检测工具调用的重复频率，
        防止 Agent 无限循环。
        """

        signature = (
            f"{tool_name}:{tool_args_json}"
        )

        count = (
            self._tool_call_history.count(
                signature
            )
        )

        # -----------------------------------------------------
        # 熔断
        # -----------------------------------------------------

        if count >= self.FUSE_THRESHOLD:

            return (
                f"检测到工具 '{tool_name}' "
                f"重复调用已达熔断阈值"
                f"（{self.FUSE_THRESHOLD}次），"
                f"已自动终止执行。"
                f"请尝试其他方案。"
            )

        # -----------------------------------------------------
        # 警告
        # -----------------------------------------------------

        elif count >= self.WARNING_THRESHOLD:

            return (
                f"警告：工具 '{tool_name}' "
                f"重复调用已达 "
                f"{self.WARNING_THRESHOLD} 次，"
                f"请检查是否有循环调用问题。"
            )

        # -----------------------------------------------------
        # 放行
        # -----------------------------------------------------

        self._tool_call_history.append(
            signature
        )

        # -----------------------------------------------------
        # 滑动窗口
        # -----------------------------------------------------

        if (
            len(self._tool_call_history)
            > self.WINDOW_SIZE
        ):

            self._tool_call_history.pop(0)

        return None

    # =========================================================
    # History
    # =========================================================

    def _save_to_history(
        self,
        messages_snapshot: list[dict]
    ) -> None:
        """保存本轮新增消息到内存历史。

        SessionManager 已经负责持久化，
        此方法主要用于更新内存中的
        _session_history。
        """

        existing_count = (
            len(self._session_history)
        )

        # 跳过 system message
        new_messages = (
            messages_snapshot[
                1 + existing_count:
            ]
        )

        self._session_history.extend(
            new_messages
        )

    # =========================================================
    # 清空历史
    # =========================================================

    def clear_history(self) -> None:
        """清空：

        1. 工具调用历史
        2. Session History
        3. Trip State
        """

        self._tool_call_history.clear()

        self._session_history.clear()

        self.trip_state.clear()

        self.session_manager.clear(
            self.session_key
        )