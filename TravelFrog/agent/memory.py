"""
记忆压缩器模块

MemoryConsolidator 负责压缩对话历史，防止 Token 超限。

当前版本采用“安全压缩”策略：
1. 检测 Token 是否超过预算
2. 保留 system prompt
3. 保留最近若干条消息
4. 将旧消息提取为简短文本摘要
5. 不再调用 LLM 生成摘要，避免压缩过程阻塞 Agent
6. 压缩记录写入 HISTORY.md
"""

import json
import os
from datetime import datetime
from typing import Any

from providers.base import LLMProvider


class MemoryConsolidator:
    """
    记忆压缩器

    当对话历史过长时，自动压缩旧消息。

    注意：
    当前版本不调用 LLM 进行摘要，避免：
        Agent -> MemoryConsolidator -> LLM
    形成额外的阻塞。
    """

    def __init__(
        self,
        provider: LLMProvider,
        workspace: str,
        token_budget: int = 32000,
    ) -> None:
        self.provider = provider
        self.workspace = workspace
        self.token_budget = token_budget

        # 保留最近多少条消息
        self.keep_recent = 6

        # 单条历史消息最多保留多少字符
        self.max_summary_chars = 8000

    # =========================================================
    # Token 估算
    # =========================================================

    def estimate_tokens(
        self,
        messages: list[dict[str, Any]]
    ) -> int:
        """
        粗略估算 Token 数量。

        中文场景下使用：
            字符数 / 2

        这是估算值，不是模型真实 Token 数。
        """

        total_chars = 0

        for msg in messages:
            try:
                msg_json = json.dumps(
                    msg,
                    ensure_ascii=False
                )
                total_chars += len(msg_json)
            except Exception:
                total_chars += len(str(msg))

        return total_chars // 2

    # =========================================================
    # 判断是否需要压缩
    # =========================================================

    async def maybe_consolidate(
        self,
        messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        如果 Token 超过预算，则压缩旧消息。

        当前采用安全压缩：
            system
            ↓
            历史摘要
            ↓
            最近 6 条消息
        """

        estimated_tokens = self.estimate_tokens(messages)

        # 没有超预算
        if estimated_tokens <= self.token_budget:
            return messages

        print(
            f"\n  🗜️ Token 预算超出"
            f"（{estimated_tokens}/{self.token_budget}）"
        )
        print("  🗜️ 开始安全压缩对话历史...")

        # =====================================================
        # 消息数量不足
        # =====================================================

        if len(messages) <= self.keep_recent + 1:
            print(
                f"  ⚠️ 消息数量较少（{len(messages)} 条），"
                f"无法进一步压缩"
            )

            # 即使不能压缩，也返回原消息
            return messages

        # =====================================================
        # 第一条通常是 system prompt
        # =====================================================

        first_msg = messages[0]

        # =====================================================
        # 最近消息
        # =====================================================

        last_messages = messages[-self.keep_recent:]

        # =====================================================
        # 中间旧消息
        # =====================================================

        old_messages = messages[
            1:-self.keep_recent
        ]

        print(
            f"  🗜️ 压缩 {len(old_messages)} 条旧消息..."
        )

        # =====================================================
        # 生成安全摘要
        # =====================================================

        summary = self._build_safe_summary(
            old_messages
        )

        summary_msg = {
            "role": "user",
            "content": (
                "【历史对话摘要，仅供上下文参考】\n"
                "以下内容来自较早的对话历史。\n"
				"它不是用户当前的新请求，请仅用于理解上下文。\n\n"
                f"{summary}"
            ),
        }

        # =====================================================
        # 构造新的消息
        # =====================================================

        compressed_messages = [
            first_msg,
            summary_msg,
			*[
				msg
        		for msg in last_messages
        		if msg.get("role") != "system"
			],
        ]

        new_tokens = self.estimate_tokens(
            compressed_messages
        )

        print(
            f"  ✅ 压缩完成："
            f"{estimated_tokens} → {new_tokens} tokens"
        )

        # =====================================================
        # 写入 HISTORY.md
        # =====================================================

        self._save_to_history(
            summary,
            len(old_messages)
        )

        return compressed_messages

    # =========================================================
    # 安全摘要
    # =========================================================

    def _build_safe_summary(
        self,
        messages: list[dict[str, Any]]
    ) -> str:
        """
        不调用 LLM。

        直接从旧消息中提取用户和助手的重要文本，
        防止压缩过程再次请求模型导致阻塞。
        """

        summary_parts: list[str] = []

        for msg in messages:
            role = msg.get("role", "")

            # =================================================
            # 工具调用消息直接跳过
            # =================================================

            if msg.get("tool_calls"):
                continue

            if msg.get("tool_call_id"):
                continue

            content = msg.get("content", "")

            if not content:
                continue

            # content 可能不是字符串
            if not isinstance(content, str):
                content = str(content)

            content = content.strip()

            if not content:
                continue

            # =================================================
            # 根据角色处理
            # =================================================

            if role == "user":
                prefix = "用户"
            elif role == "assistant":
                prefix = "助手"
            elif role == "system":
                prefix = "系统"
            else:
                prefix = role or "未知"

            # =================================================
            # 单条消息限制长度
            # =================================================

            if len(content) > 1500:
                content = content[:1500] + "……"

            summary_parts.append(
                f"{prefix}：{content}"
            )

        # =====================================================
        # 没有可提取内容
        # =====================================================

        if not summary_parts:
            return "较早对话主要包含工具调用和执行过程，详细工具结果已省略。"

        # =====================================================
        # 合并
        # =====================================================

        summary = "\n".join(summary_parts)

        # =====================================================
        # 总长度限制
        # =====================================================

        if len(summary) > self.max_summary_chars:
            summary = (
                summary[:self.max_summary_chars]
                + "\n……更早的对话内容已省略。"
            )

        return summary

    # =========================================================
    # 写入 HISTORY.md
    # =========================================================

    def _save_to_history(
        self,
        summary: str,
        original_count: int
    ) -> None:
        """
        将压缩记录写入 HISTORY.md。
        """

        history_dir = os.path.join(
            self.workspace,
            "workspace",
            "memory"
        )

        history_file = os.path.join(
            history_dir,
            "HISTORY.md"
        )

        os.makedirs(
            history_dir,
            exist_ok=True
        )

        current_time = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        content = f"""## {current_time}

压缩了 {original_count} 条旧消息

{summary}

---

"""

        try:
            with open(
                history_file,
                "a",
                encoding="utf-8"
            ) as f:
                f.write(content)

        except Exception as e:
            print(
                f"  ⚠️ 写入 HISTORY.md 失败：{e}"
            )