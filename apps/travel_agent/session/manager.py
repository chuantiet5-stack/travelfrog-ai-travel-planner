"""
会话管理器模块

SessionManager 负责持久化存储 Agent 的对话历史以及旅行状态，包括：
- 按会话 key 分组存储消息（JSONL 格式）
- 加载历史对话记录
- 清除指定会话
- 列出所有已保存的会话
- 保存旅行状态 trip_state
- 加载旅行状态 trip_state
- 清除旅行状态

会话文件存储在 workspace/sessions 目录下：

    普通会话：
        cli_direct.jsonl

    旅游会话：
        travel_2_a81f39d2.jsonl
        travel_2_a81f39d2_trip_state.json

其中：
    .jsonl                  -> Agent 对话历史
    _trip_state.json        -> 当前旅行结构化状态

使用示例：

    manager = SessionManager()

    # 保存消息
    manager.save_message(
        "cli:direct",
        {"role": "user", "content": "你好"}
    )

    # 加载历史
    history = manager.get_history("cli:direct")

    # 保存旅行状态
    manager.save_trip_state(
        "travel:2:a81f39d2",
        {
            "trip_id": "a81f39d2",
            "destination": "杭州",
            "days": 3,
            "budget": "3000元左右",
            "people": "情侣",
            "style": ["古韵文化", "美食", "自然风景"],
            "pace": "轻松",
            "special_requirements": [
                "不要安排得太赶"
            ],
            "status": "planning"
        }
    )

    # 加载旅行状态
    trip_state = manager.get_trip_state(
        "travel:2:a81f39d2"
    )

    # 清除会话
    manager.clear("travel:2:a81f39d2")
"""

import json
import os
from datetime import datetime
from typing import Any


class SessionManager:
    """
    会话管理器

    持久化存储 Agent 的：
    1. 对话历史
    2. 当前旅行状态 trip_state

    所有数据文件存储在 workspace/sessions/ 目录下。
    """

    def __init__(
        self,
        sessions_dir: str = "workspace/sessions"
    ) -> None:
        """
        Args:
            sessions_dir:
                会话文件存储目录，
                默认 "workspace/sessions"
        """

        self.sessions_dir = sessions_dir

        # 自动创建目录
        os.makedirs(
            self.sessions_dir,
            exist_ok=True
        )

    # =========================================================
    # Session 文件路径
    # =========================================================

    def _get_session_path(
        self,
        session_key: str
    ) -> str:
        """
        获取会话 JSONL 文件路径。

        例如：

            travel:2:a81f39d2

        转换为：

            workspace/sessions/
            travel_2_a81f39d2.jsonl
        """

        safe_key = session_key.replace(":", "_")

        return os.path.join(
            self.sessions_dir,
            f"{safe_key}.jsonl"
        )

    # =========================================================
    # Trip State 文件路径
    # =========================================================

    def _get_trip_state_path(
        self,
        session_key: str
    ) -> str:
        """
        获取旅行状态文件路径。

        例如：

            travel:2:a81f39d2

        对应：

            workspace/sessions/
            travel_2_a81f39d2_trip_state.json
        """

        safe_key = session_key.replace(":", "_")

        return os.path.join(
            self.sessions_dir,
            f"{safe_key}_trip_state.json"
        )

    # =========================================================
    # 保存消息
    # =========================================================

    def save_message(
        self,
        session_key: str,
        message: dict[str, Any]
    ) -> None:
        """
        保存消息到会话文件。

        JSONL 每一行保存一条消息。

        Args:
            session_key:
                会话标识符

            message:
                消息字典，例如：

                {
                    "role": "user",
                    "content": "你好"
                }
        """

        file_path = self._get_session_path(
            session_key
        )

        # 添加时间戳
        message_with_timestamp = message.copy()

        message_with_timestamp["timestamp"] = (
            datetime.now().isoformat()
        )

        try:
            with open(
                file_path,
                "a",
                encoding="utf-8"
            ) as f:

                json_line = json.dumps(
                    message_with_timestamp,
                    ensure_ascii=False
                )

                f.write(
                    json_line + "\n"
                )

        except Exception as e:

            print(
                f"警告: 保存消息失败 - {e}"
            )

    # =========================================================
    # 加载历史
    # =========================================================

    def get_history(
        self,
        session_key: str
    ) -> list[dict[str, Any]]:
        """
        加载会话历史。

        返回消息列表，并自动去掉 timestamp 字段。
        """

        file_path = self._get_session_path(
            session_key
        )

        if not os.path.isfile(file_path):
            return []

        history: list[dict[str, Any]] = []

        try:

            with open(
                file_path,
                "r",
                encoding="utf-8"
            ) as f:

                for line in f:

                    if not line.strip():
                        continue

                    try:

                        message = json.loads(line)

                        message_copy = message.copy()

                        # OpenAI API 不需要 timestamp
                        message_copy.pop(
                            "timestamp",
                            None
                        )

                        history.append(
                            message_copy
                        )

                    except json.JSONDecodeError:

                        # 跳过损坏的 JSON 行
                        continue

        except Exception as e:

            print(
                f"警告: 加载历史失败 - {e}"
            )

            return []

        return history

    # =========================================================
    # 保存旅行状态
    # =========================================================

    def save_trip_state(
        self,
        session_key: str,
        state: dict[str, Any]
    ) -> None:
        """
        保存当前旅行状态。

        trip_state 与聊天历史分开保存。

        例如：

        {
            "trip_id": "a81f39d2",
            "destination": "杭州",
            "start_date": null,
            "days": 3,
            "budget": "3000元左右",
            "people": "情侣",
            "style": [
                "古韵文化",
                "美食",
                "自然风景"
            ],
            "pace": "轻松",
            "special_requirements": [
                "不要安排得太赶"
            ],
            "status": "planning"
        }
        """

        file_path = self._get_trip_state_path(
            session_key
        )

        try:

            with open(
                file_path,
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    state,
                    f,
                    ensure_ascii=False,
                    indent=2
                )

        except Exception as e:

            print(
                f"警告: 保存旅行状态失败 - {e}"
            )

    # =========================================================
    # 加载旅行状态
    # =========================================================

    def get_trip_state(
        self,
        session_key: str
    ) -> dict[str, Any]:
        """
        加载当前旅行状态。

        如果不存在旅行状态文件，
        返回空字典。
        """

        file_path = self._get_trip_state_path(
            session_key
        )

        if not os.path.isfile(file_path):
            return {}

        try:

            with open(
                file_path,
                "r",
                encoding="utf-8"
            ) as f:

                state = json.load(f)

                if isinstance(state, dict):
                    return state

                return {}

        except json.JSONDecodeError:

            print(
                f"警告: 旅行状态 JSON 格式错误: "
                f"{file_path}"
            )

            return {}

        except Exception as e:

            print(
                f"警告: 加载旅行状态失败 - {e}"
            )

            return {}

    # =========================================================
    # 更新旅行状态
    # =========================================================

    def update_trip_state(
        self,
        session_key: str,
        updates: dict[str, Any]
    ) -> dict[str, Any]:
        """
        增量更新旅行状态。

        不会覆盖整个 trip_state，
        而是在已有状态基础上进行更新。

        例如原状态：

        {
            "destination": "杭州",
            "days": 3,
            "pace": "适中"
        }

        更新：

        {
            "pace": "轻松"
        }

        最终：

        {
            "destination": "杭州",
            "days": 3,
            "pace": "轻松"
        }

        Returns:
            dict:
                更新后的完整旅行状态。
        """

        current_state = self.get_trip_state(
            session_key
        )

        # 更新普通字段
        for key, value in updates.items():

            # None 不覆盖原来的有效值
            if value is None:
                continue

            current_state[key] = value

        # 保存
        self.save_trip_state(
            session_key,
            current_state
        )

        return current_state

    # =========================================================
    # 清除旅行状态
    # =========================================================

    def clear_trip_state(
        self,
        session_key: str
    ) -> None:
        """
        清除指定会话的旅行状态。
        """

        file_path = self._get_trip_state_path(
            session_key
        )

        if os.path.isfile(file_path):

            try:

                os.remove(file_path)

            except Exception as e:

                print(
                    f"警告: 清除旅行状态失败 - {e}"
                )

    # =========================================================
    # 清除会话
    # =========================================================

    def clear(
        self,
        session_key: str
    ) -> None:
        """
        清除指定会话。

        同时清除：

        1. 对话历史 JSONL
        2. trip_state JSON
        """

        # -----------------------------------------------------
        # 清除聊天历史
        # -----------------------------------------------------

        file_path = self._get_session_path(
            session_key
        )

        if os.path.isfile(file_path):

            try:

                os.remove(file_path)

            except Exception as e:

                print(
                    f"警告: 清除会话失败 - {e}"
                )

        # -----------------------------------------------------
        # 清除旅行状态
        # -----------------------------------------------------

        self.clear_trip_state(
            session_key
        )

    # =========================================================
    # 列出所有会话
    # =========================================================

    def list_sessions(
        self
    ) -> list[str]:
        """
        列出所有已保存的会话。

        只扫描 .jsonl 文件，
        不会把 trip_state.json
        当成独立会话。
        """

        sessions: list[str] = []

        if not os.path.isdir(
            self.sessions_dir
        ):
            return sessions

        try:

            for filename in os.listdir(
                self.sessions_dir
            ):

                # 只处理 JSONL 会话文件
                if not filename.endswith(
                    ".jsonl"
                ):
                    continue

                safe_key = filename[:-6]

                session_key = safe_key.replace(
                    "_",
                    ":"
                )

                sessions.append(
                    session_key
                )

        except Exception:

            pass

        return sessions