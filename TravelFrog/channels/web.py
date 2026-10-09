"""Web 渠道实现模块，提供 WebSocket + 旅游规划 HTTP 接口。"""


import json
import re
import uuid
from pathlib import Path
from typing import Any, Callable
import asyncio
import urllib.parse
import httpx
from PIL import Image
from io import BytesIO
from fastapi.responses import Response
from fastapi import Request as FastAPIRequest

import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import HTMLResponse

from bus import InboundMessage, MessageBus, OutboundMessage
from .base import Channel


class TravelPlanRequest(BaseModel):
    """旅游规划请求。"""

    session_key: str
    destination: str
    preference: dict
    spots: list = []
    message: str = ""


class WebChannel(Channel):
    """Web 渠道，通过 WebSocket 和 HTTP 接口提供服务。"""

    def __init__(
        self,
        bus: MessageBus,
        host: str = "0.0.0.0",
        port: int = 8080,
        agent_factory: Callable[[str], Any] | None = None,
    ):
        """初始化 Web 渠道。

        Args:
            bus: 消息总线实例
            host: 监听地址
            port: 监听端口
            agent_factory: Agent 创建函数，接收 session_key
        """
        super().__init__(name="web", bus=bus)

        self.host = host
        self.port = port

        # NanoClaw Agent 工厂
        self.agent_factory = agent_factory

        # HTTP 旅游规划接口使用的 Agent 缓存
        # session_key -> AgentLoop
        self._agents: dict[str, Any] = {}

        # WebSocket 连接
        # client_id -> WebSocket
        self._connections: dict[str, WebSocket] = {}

        self._app: FastAPI | None = None
        self._server: uvicorn.Server | None = None

    async def start(self) -> None:
        """启动 FastAPI + WebSocket 服务。"""

        self._app = FastAPI(title="NanoClaw Web")

        self._app.add_middleware(
            CORSMiddleware,
            allow_origins=[
                "http://127.0.0.1:5001",
                "http://localhost:5001",
            ],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # 注册路由
        self._register_routes()

        print(
            f"[WebChannel] 正在启动 Web 服务: "
            f"http://{self.host}:{self.port}"
        )

        config = uvicorn.Config(
            self._app,
            host=self.host,
            port=self.port,
            log_level="info",
        )

        self._server = uvicorn.Server(config)

        await self._server.serve()

    def _register_routes(self) -> None:
        """注册 FastAPI 路由。"""

        if self._app is None:
            return

        # 请求头（反防盗链关键：Referer 置空，百度对空 Referer 放行率最高）
        _BAIDU_IMG_HEADERS = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": "",
        }

        # SVG 占位兜底图（失败时返回，永无破图红叉）
        _PLACEHOLDER_SVG = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="360" '
            'viewBox="0 0 800 360">'
            '<rect width="100%" height="100%" fill="#f0f0f0"/>'
            '<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" '
            'font-family="sans-serif" font-size="22" fill="#999">景点图片加载中</text>'
            '</svg>'
        )

        @self._app.get("/proxy_img")
        async def proxy_img(remote_url: str = "", request: FastAPIRequest = None):
            """后端图片代理：把远程图片二进制透传给浏览器。"""
            if not remote_url:
                return Response(content=_PLACEHOLDER_SVG.encode("utf-8"),
                                media_type="image/svg+xml")
            try:
                # 从 remote_url 提取域名作为 Referer，解决防盗链问题
                referer = ""
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(remote_url)
                    if parsed.netloc:
                        # 取协议+域名作为 Referer（如 https://hotels.ctrip.com）
                        # 但图片域名和页面域名可能不同，退而用图片自身域名
                        referer = f"{parsed.scheme}://{parsed.netloc}/"
                except Exception:
                    pass
                fetch_headers = dict(_BAIDU_IMG_HEADERS)
                if referer:
                    fetch_headers["Referer"] = referer
                timeout = httpx.Timeout(20.0, connect=10.0)
                async with httpx.AsyncClient(timeout=timeout,
                                            follow_redirects=True) as client:
                    resp = await client.get(remote_url, headers=fetch_headers)
                if (
                    resp.status_code != 200
                    or len(resp.content) < 200
                    or len(resp.content) > 15 * 1024 * 1024
                ):
                    # 超过15MB直接拒绝：超大图进 PIL 打开会瞬间抬升内存
                    raise ValueError(f"bad status/size: {resp.status_code}/{len(resp.content)}")
                ctype = resp.headers.get("Content-Type", "image/jpeg")
                if not ctype or ctype.startswith("text/"):
                    ctype = "image/jpeg"
                headers = {
                    "Cache-Control": "public, max-age=86400",  # 浏览器缓存24h
                    "Access-Control-Allow-Origin": "*",
                }
                try:

                    # 图片压缩
                    img = Image.open(
                        BytesIO(resp.content)
                    )

                    # 转 RGB 防止 PNG 透明问题
                    if img.mode != "RGB":
                        img = img.convert("RGB")

                    # 最大尺寸限制
                    max_size = 1200

                    img.thumbnail(
                        (max_size, max_size)
                    )

                    buffer = BytesIO()

                    # JPEG压缩
                    img.save(
                        buffer,
                        format="JPEG",
                        quality=75,
                        optimize=True
                    )

                    compressed = buffer.getvalue()

                    print(
                        "[proxy_img] 压缩:",
                        len(resp.content)//1024,
                        "KB ->",
                        len(compressed)//1024,
                        "KB"
                    )

                    return Response(
                        content=compressed,
                        media_type="image/jpeg",
                        headers=headers
                    )

                except Exception as e:

                    print(
                        "图片压缩失败:",
                        e
                    )

                    return Response(
                        content=resp.content,
                        media_type=ctype
                    )
            except Exception as e:
                print(f"[WebChannel] proxy_img 失败: {e} -> 返回占位图")
                return Response(content=_PLACEHOLDER_SVG.encode("utf-8"),
                                media_type="image/svg+xml",
                                headers={"Access-Control-Allow-Origin": "*"})

        # 0.6 /voice2text — 语音转文字（输入框录音 → 硅基流动 ASR）
        _SILICONFLOW_KEY = ""
        try:
            _cfg_path = Path(__file__).resolve().parent.parent / "config.json"
            _SILICONFLOW_KEY = json.loads(_cfg_path.read_text("utf-8")).get("api_key", "")
        except Exception as _e:
            print(f"[WebChannel] 读取 config.json api_key 失败: {_e}")

        @self._app.post("/voice2text")
        async def voice2text(request: FastAPIRequest):
            """语音转文字：接收 WAV 音频原始字节，转发硅基流动识别。"""
            _resp_headers = {"Access-Control-Allow-Origin": "*"}
            if not _SILICONFLOW_KEY:
                return Response(content=json.dumps({"error": "后端未配置 api_key"},
                                ensure_ascii=False), media_type="application/json",
                                headers=_resp_headers)
            audio = await request.body()
            if not audio or len(audio) < 1000:
                return Response(content=json.dumps({"error": "音频为空或太短"},
                                ensure_ascii=False), media_type="application/json",
                                headers=_resp_headers)
            if len(audio) > 15 * 1024 * 1024:
                return Response(content=json.dumps({"error": "音频过大(>15MB)"},
                                ensure_ascii=False), media_type="application/json",
                                headers=_resp_headers)
            try:
                import time as _time
                import traceback as _tb
                _t0 = _time.time()
                # 硅基流动免费 ASR 排队常达 20-45s：单次读超时收紧到 20s，
                # 卡住的请求快速轮换重试（最多 3 次尝试）
                timeout = httpx.Timeout(20.0, connect=8.0)
                # trust_env=False：绕过系统代理直连硅基流动（国内可直连，
                # 系统代理不稳定是偶发"空异常"失败的主因之一）
                # 自动重试：网络抖动/断连偶发，最多 3 次，间隔递增
                resp = None
                last_err: Exception | None = None
                for attempt in range(3):
                    try:
                        async with httpx.AsyncClient(
                            timeout=timeout, trust_env=False
                        ) as client:
                            resp = await client.post(
                                "https://api.siliconflow.cn/v1/audio/transcriptions",
                                headers={"Authorization": f"Bearer {_SILICONFLOW_KEY}"},
                                files={"file": ("audio.wav", audio, "audio/wav")},
                                data={"model": "FunAudioLLM/SenseVoiceSmall"},
                            )
                        break
                    except Exception as retry_e:
                        last_err = retry_e
                        print(
                            f"[WebChannel] voice2text 第{attempt + 1}次请求失败: "
                            f"{type(retry_e).__name__}: {retry_e}"
                        )
                        if attempt < 2:
                            import asyncio as _aio
                            await _aio.sleep(0.8 * (attempt + 1))
                if resp is None:
                    # 异常类型名一定非空，前端提示不再出现空消息
                    raise RuntimeError(
                        f"{type(last_err).__name__}: {last_err}" if last_err else "未知网络错误"
                    )
                if resp.status_code != 200:
                    return Response(content=json.dumps(
                        {"error": f"识别失败({resp.status_code}): " + resp.text[:200]},
                        ensure_ascii=False), media_type="application/json",
                        headers=_resp_headers)
                text = (resp.json() or {}).get("text", "")
                print(
                    f"[WebChannel] voice2text 完成: "
                    f"{len(audio)/1024:.0f}KB -> {len(text)}字, "
                    f"耗时 {_time.time() - _t0:.1f}s"
                )
                return Response(content=json.dumps({"text": text}, ensure_ascii=False),
                                media_type="application/json", headers=_resp_headers)
            except Exception as e:
                # 打印完整堆栈，空消息异常也能定位
                print(f"[WebChannel] voice2text 异常: {type(e).__name__}: {e}")
                print(_tb.format_exc())
                return Response(content=json.dumps(
                    {"error": f"语音服务异常({type(e).__name__}): {str(e)[:100]}"},
                    ensure_ascii=False), media_type="application/json",
                    headers=_resp_headers)

        _IMG_HEADERS = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "image/png,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        async def _fetch_attraction_image(name: str, city: str = "") -> str | None:
            query = f"{city} {name}".strip()
            timeout = httpx.Timeout(20.0, connect=10.0)

            # ===== 主源：百度 acjson =====
            try:
                async with httpx.AsyncClient(
                    timeout=timeout,
                    follow_redirects=True,
                    headers=_BAIDU_IMG_HEADERS,
                ) as client:
                    resp = await client.get(
                        "https://image.baidu.com/search/acjson",
                        params={
                            "tn": "resultjson_com",
                            "word": query,
                            "queryWord": query,
                            "pn": 0,
                            "rn": 5,
                            "ipn": "rj",
                            "fp": "result",
                            "cl": 2, "lm": -1, "st": -1, "face": 0,
                            "istype": 2, "nc": 1,
                            "ie": "utf-8", "oe": "utf-8",
                            "ct": 201326592,
                        },
                    )
                data = resp.json()
            except Exception as e:
                print(f"[WebChannel] _fetch_attraction_image 百度主源异常: {e}")
                data = None

            # 百度返回 antiFlag 时不直接 return None，fall through 到必应
            if isinstance(data, dict) and data.get("antiFlag"):
                print(
                    f"  [百度] query={query!r} 被反爬拦截: "
                    f"{data.get('message')}"
                )
                data = None
            elif isinstance(data, dict):
                items = data.get("data", []) or []
                cands = []  # (url, width, height)
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    src = (
                        it.get("middleURL")
                        or it.get("thumbURL")
                        or it.get("objURL")
                    )
                    if not src:
                        continue
                    s = str(src).strip()
                    if s.startswith("//"):
                        s = "https:" + s
                    if s.startswith("http://"):
                        s = "https://" + s[7:]
                    if s.startswith("http"):
                        try:
                            w = int(it.get("width") or 0)
                            h = int(it.get("height") or 0)
                        except Exception:
                            w = h = 0
                        cands.append((s, w, h))
                if cands:
                    # 优先横图（宽>=高 且 宽>=500）：实拍图多为横图，
                    # 避开"XX美食地图"这类竖版营销海报
                    for s, w, h in cands:
                        if w and h and w >= h and w >= 500:
                            print(f"  [百度] query={query!r} 命中(横图 {w}x{h})")
                            return s
                    s, w, h = cands[0]
                    print(f"  [百度] query={query!r} 命中(兜底 {w}x{h})")
                    return s
                print(f"  [百度] query={query!r} 未抽出可用 URL")

            # ===== 兑底：必应图片（百度被拦截/无图时才调） =====
            try:
                async with httpx.AsyncClient(
                    timeout=timeout,
                    follow_redirects=True,
                    headers=_IMG_HEADERS,
                ) as client:
                    resp = await client.get(
                        "https://www.bing.com/images/search",
                        params={
                            "q": query,
                            "form": "HDRSC2",
                            "first": 1,
                            "count": 5,
                        },
                    )
                html = resp.text
            except Exception as e:
                print(f"[WebChannel] _fetch_attraction_image 必应兑底异常: {e}")
                return None

            if html:
                # 必应页面里嵌有 m="..." 字段，含原始图片 URL
                urls = re.findall(r"murl&quot;:&quot;(https?://[^&\"']+)", html)
                # 充分过滤：跳过 svg/小图标/占位图
                bad_ext = (".svg", ".gif", ".webp?")
                for u in urls:
                    low = u.lower().split("?")[0]
                    if low.endswith(bad_ext):
                        continue
                    if len(u) < 30:
                        continue
                    if u.startswith("//"):
                        u = "https:" + u
                    if u.startswith("http://"):
                        u = "https://" + u[7:]
                    if u.startswith("http"):
                        print(f"  [必应] query={query!r} 命中（兑底）")
                        return u
                print(f"  [必应] query={query!r} status={resp.status_code} 未抽出可用 URL")

            return None


        # ==========================================================
        # 1. Web 首页
        # ==========================================================

        @self._app.get("/")
        async def index():
            """返回 Web UI 页面。"""

            index_path = (
                Path(__file__).parent
                / "web_ui"
                / "index.html"
            )

            if index_path.exists():
                return HTMLResponse(
                    content=index_path.read_text(
                        encoding="utf-8"
                    )
                )

            return HTMLResponse(
                content="<h1>index.html not found</h1>"
            )

        # ==========================================================
        # 2. WebSocket /ws
        # ==========================================================

        @self._app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket 连接处理。"""

            await websocket.accept()

            client_id = str(uuid.uuid4())

            self._connections[client_id] = websocket

            print(
                f"[WebChannel] 新连接: "
                f"client_id={client_id}"
            )

            try:
                while True:
                    data = await websocket.receive_text()

                    try:
                        payload = json.loads(data)
                    except Exception:
                        payload = {"message": data}

                    message = InboundMessage(
                        channel="web",
                        sender_id=client_id,
                        chat_id=client_id,
                        content=json.dumps(
                            payload,
                            ensure_ascii=False,
                        ),
                        raw={
                            "client_id": client_id,
                            # ⭐ 保存旅游结构化参数
                            "travel_data": payload,
                        },
                    )

                    await self.bus.publish_inbound(message)

            except Exception as e:
                print(
                    f"[WebChannel] 连接断开: "
                    f"client_id={client_id} "
                    f"reason={e}"
                )

            finally:
                self._connections.pop(
                    client_id,
                    None,
                )

        # ==========================================================
        # 3. 旅游规划 HTTP API
        # ==========================================================

        @self._app.post("/api/travel/plan")
        async def travel_plan(request: TravelPlanRequest):
            """调用 NanoClaw Agent 生成旅游攻略。"""

            print(
                "[WebChannel] 收到旅游规划请求:"
                f" session_key={request.session_key}"
                f" destination={request.destination}"
            )

            # ------------------------------------------------------
            # 检查 Agent 工厂
            # ------------------------------------------------------

            if self.agent_factory is None:
                return {
                    "success": False,
                    "message": "Agent 工厂未配置，无法进行旅游规划。",
                }

            # ------------------------------------------------------
            # 获取 / 创建 Agent
            # ------------------------------------------------------

            session_key = request.session_key.strip()

            if not session_key:
                session_key = (
                    f"travel:"
                    f"{uuid.uuid4().hex}"
                )

            agent = self._agents.get(session_key)

            if agent is None:
                try:
                    agent = self.agent_factory(session_key)

                    self._agents[session_key] = agent

                    print(
                        "[WebChannel] 创建旅游 Agent:"
                        f" {session_key}"
                    )

                except Exception as e:
                    print(
                        "[WebChannel] 创建 Agent 失败:"
                        f" {e}"
                    )

                    return {
                        "success": False,
                        "message": (
                            f"创建旅行 Agent 失败：{str(e)}"
                        ),
                    }

            # ------------------------------------------------------
            # 构造旅游规划 Prompt
            # ------------------------------------------------------

            preference = request.preference or {}
            spots = request.spots or []

            prompt = f"""
你现在处于“旅游规划模式”。

这是一次旅游规划任务，必须使用：
skills/trip_planner/SKILL.md

请先读取：
skills/trip_planner/SKILL.md

严格按照该技能中的流程执行。

========================
一、核心任务
========================

你的任务是：
理解用户真实旅行需求 → 补全旅行参数 → 查询真实旅游信息 → 制定旅行方案。

注意：

你不能因为结构化字段为空，就认为用户没有提供旅行信息。

如果【目的地城市】为空，或者【用户旅游偏好】中的部分字段为“未指定”，
必须优先从【用户额外需求】中提取用户已经表达的信息。

例如：

用户说：
“我想去杭州玩3天，和女朋友一起，预算3000元左右，
喜欢古韵文化、美食和自然风景，希望行程轻松一点，不要安排得太赶。”

你必须识别出：

- 目的地：杭州
- 游玩天数：3天
- 出行人群：情侣
- 预算：3000元左右
- 旅行风格：古韵文化、美食、自然风景
- 旅行节奏：轻松，不要安排过于紧凑

然后直接开始旅行规划。

不能只回复：
“好的，我已经了解你的需求。”
也不能只复述用户需求。

必须继续执行后续的工具查询和旅行规划。

========================
二、信息来源优先级
========================

旅行需求信息按照以下优先级理解：

第一优先级：
【用户额外需求】

第二优先级：
【用户旅游偏好】

第三优先级：
【旅游推荐系统候选景点】

如果不同信息之间存在冲突：

1. 用户额外需求优先。
2. 用户最新、最明确的表达优先。
3. 不要因为发现冲突而要求用户确认。
4. 自动采用更加明确、更加具体的用户需求。

========================
三、用户自然语言信息提取
========================

在开始规划之前，必须检查以下信息：

- 目的地
- 出发时间/季节
- 游玩天数
- 预算
- 出行人数/同行人群
- 旅行风格
- 旅行节奏
- 用户特殊要求

如果结构化字段已经提供，则使用结构化字段。

如果结构化字段为空，则必须从【用户额外需求】中提取。

特别是“直接规划”模式下：

【目的地城市】可能为空；
【用户旅游偏好】可能为空；
【旅游推荐系统候选景点】可能为空。

此时【用户额外需求】是主要需求来源。

如果用户已经提供了足够的信息，则不要反问用户，直接完成规划。

========================
四、工具使用要求
========================

不允许仅凭模型自身知识直接生成具体旅行攻略。

在制定具体景点、路线、天气、交通等信息之前，
应优先使用可用的旅游工具获取真实信息。

优先使用：

- amap__search_poi
- amap__search_around

查询：

- 景点
- 景点地址
- 景点基本信息
- 景点之间的位置关系
- 必要时查询周边餐饮等信息

需要天气信息时使用：

- seniverse__get_weather_now
- seniverse__get_weather_forecast

工具返回的信息作为旅行规划的重要依据。

不要虚构：

- 景点
- 餐厅
- 景点地址
- 开放时间
- 门票价格
- 天气
- 交通方式
- 交通时间
- 交通费用
- 联系方式

如果工具没有返回具体信息，不要自行编造具体数字。

========================
五、旅游推荐系统候选景点
========================

【旅游推荐系统候选景点】：

{spots}

如果候选景点不为空：

1. 优先参考候选景点。
2. 候选景点是根据用户偏好筛选出的候选结果。
3. 可以使用高德地图 MCP 对候选景点进行查询和验证。
4. 可以根据用户实际需求调整候选景点的优先级。
5. 如果候选景点不足，可以使用高德地图 MCP 补充景点。
6. 不要因为候选景点数量少而限制最终旅行攻略。

如果候选景点为空：

说明当前属于“直接规划”模式。

此时必须根据用户自然语言中提取出的目的地和需求，
主动使用高德地图 MCP 查询适合的景点。


🔴🔴🔴 景点图片 —— 后端代理方案，Agent 严禁输出图片 🔴🔴🔴

⚠️ 【你（Agent）不需要、也绝对不允许输出任何图片内容】：
   - ❌ 禁止调用 baidutupian__get_attraction_image / search_photos 等任何图片工具
   - ❌ 禁止在行程正文里插入任何 ![alt](url) Markdown 图片语法
   - ❌ 禁止输出 <img src=...> 等 HTML 标签
   - ❌ 禁止把任何 URL 当成图片地址写进行程正文里

✅ 【正确做法】：景点按 Markdown 小标题格式输出即可：
   - 景点标题使用 ### 或 #### 层级，例如：
     ### 上午：丽江古城
     #### 木府
     ### 第一站: 颐和园
   - 每个景点一个独立小标题（把景点名写在标题文本里，不要藏在正文）
   - 【后端会自动读取所有景点小标题，为每个景点插好图片】，你不用操心
   - 特色美食也必须用独立小标题输出（不要只写一列文字清单），例如：
     #### 九转大肠（鲁菜名菜）
     #### 芙蓉街小吃
     #### 威海海鲜水饺
   - 每个推荐美食/美食街一个 #### 小标题，美食名写在标题文本里
   - 【后端会自动为美食小标题配上美食图片】，你不用操心

输出保持：结构清晰的纯 Markdown 文本（标题/列表/粗体），无任何图片、任何外链、任何 HTML。

========================
六、当前旅行信息
========================

【目的地城市】
{request.destination or "未通过结构化字段提供，需要从用户额外需求中提取"}

【用户旅游偏好】
- 季节：{preference.get("season", "未指定")}
- 旅行风格：{preference.get("style_type", "未指定")}
- 预算：{preference.get("budget_level", "未指定")}
- 游玩天数：{preference.get("play_days", "未指定")}
- 出行人群：{preference.get("people_type", "未指定")}

【用户偏好重要程度】
{preference.get("priority", {})}

【用户额外需求】
{request.message or "暂无额外需求"}

========================
七、旅行规划流程
========================

必须按照以下流程执行：

第一步：理解用户需求

从结构化字段和自然语言中提取完整旅行需求。

第二步：确定目的地

如果 request.destination 不为空，使用该目的地。

如果 request.destination 为空：

必须从用户额外需求中提取目的地。

例如：
“我想去杭州玩3天”
→ 目的地 = 杭州

第三步：确定旅行参数

从用户自然语言中提取：

- 天数
- 预算
- 同行人群
- 旅行风格
- 旅行节奏
- 特殊要求

第四步：查询真实旅游信息

根据确定的目的地和用户需求：

优先使用高德地图 MCP 查询景点。

如果需要天气信息，则使用心知天气 MCP 查询。

第五步：筛选和排序景点

结合：

- 用户旅行风格
- 用户预算
- 用户游玩天数
- 同行人群
- 用户特殊要求
- 旅游推荐系统候选景点
- 工具查询结果

选择适合的景点。

第六步：制定路线

根据景点之间的位置关系安排合理路线。

注意：

用户如果要求“轻松一点”“不要太赶”，
必须减少每天景点数量，合理安排休息时间。

不能只在文字中说“行程轻松”，
必须真正体现在每日行程安排中。

第七步：预算规划

结合用户预算给出合理的费用建议。

没有工具确认的具体价格，不得编造。

如果无法确认具体价格，
可以给出费用构成和预算分配建议，
但必须明确说明具体价格以实际平台或景区最新信息为准。

第八步：生成最终攻略

直接输出完整、清晰、可以执行的旅行攻略。

========================
八、最终输出要求
========================

最终攻略至少包括：

1. 旅行概览
2. 用户需求分析
3. 每日详细行程
4. 景点安排
5. 景点游览顺序
6. 景点之间的交通建议
7. 餐饮建议
8. 预算建议
9. 天气建议（如果查询到了天气）
10. 注意事项

如果用户要求轻松旅行：

每天不要安排过多景点；
避免过度折返；
适当安排午餐、休息和自由活动时间。

========================
九、可靠性要求
========================

工具查询结果优先于模型自身知识。

对于以下信息：

- 景点地址
- 开放时间
- 门票
- 天气
- 交通
- 交通时间
- 交通费用

如果没有工具确认，不得伪造具体数值。

最终输出时，应区分：

【工具确认信息】
工具实际查询得到的信息。

【旅蛙规划建议】
基于用户需求进行的路线、景点和时间安排。

【未确认信息】
无法通过工具确认的信息，需要明确说明以实际情况为准。

========================
十、最重要的执行规则
========================

1. 必须先读取 skills/trip_planner/SKILL.md。
2. 不允许只凭模型自身知识生成旅行攻略。
3. destination 为空时，必须从用户自然语言中提取目的地。
4. preference 为空或字段缺失时，必须从用户自然语言中提取旅行参数。
5. spots 为空时，必须主动通过旅游工具查询景点。
6. 有候选景点时优先参考候选景点。
7. 用户额外需求优先级最高。
8. 用户要求轻松旅行时，必须真正降低行程密度。
9. 除非缺少完成规划所必需的核心信息，否则不要反问用户。
10. 不要只输出需求分析。
11. 不要只回复“已经了解你的需求”。
12. 不要询问“是否确认”。
13. 必须直接完成旅行规划。
14. 必须调用必要的旅游工具获取真实信息。
15. 最终输出一份完整、合理、可执行的旅行攻略。

现在开始执行旅游规划任务。
"""

            print(
                "[WebChannel] 正在调用 NanoClaw Agent..."
            )

            # ------------------------------------------------------
            # 调用 NanoClaw Agent
            # ------------------------------------------------------

            try:
                result = await agent.run(prompt)

            except Exception as e:
                print(
                    "[WebChannel] Agent 执行失败:"
                    f" {e}"
                )

                return {
                    "success": False,
                    "message": (
                        f"旅行规划执行失败：{str(e)}"
                    ),
                }

            # 第1步：防御式清理——剥离 Agent 误输出的残留图片语法/img标签
            result = re.sub(r"!\[[^\]]*\]\([^)]*\)\s*", "", result)
            result = re.sub(r"<img\b[^>]*>\s*", "", result, flags=re.IGNORECASE)

            try:
                # 第2步：正则提取 ## ~ #### 小标题里的名称
                # （## 二级标题仅用于识别"美食板块"，本身不配图）
                _ATTR_RE = re.compile(
                    r"^(#{2,4})\s*"
                    r"(?:[^\n\r:：]*?[:：]\s*)?"   # 兼容 "### 上午：趵突泉景区（13:30-17:30）"
                    r"([^\r\n]{2,60})",
                    re.MULTILINE,
                )
                matches = list(_ATTR_RE.finditer(result))

                # 列表项匹配："1. 重庆小面：重庆传统早餐" / "2、火锅：xxx"
                # （Agent 常以编号列表输出美食，提取冒号前的名称来配图）
                _LIST_RE = re.compile(
                    r"^\s*\d{1,2}\s*[.、)）]\s*([^\n:：，,。！!？?]{2,24})(?=\s*[：:])",
                    re.MULTILINE,
                )
                # 标题与列表项合并后按文中位置排序，保证板块状态（美食上下文）判定正确
                segs = []  # (start, name_end, 原始文本, 标题级别)
                for m in matches:
                    segs.append((m.start(), m.end(), m.group(2).strip(), m.group(1)))
                for m in _LIST_RE.finditer(result):
                    segs.append((m.start(), m.end(), m.group(1).strip(), ""))
                segs.sort(key=lambda x: x[0])

                # 第3步：三张关键词表
                # 白名单：景点关键词（命中 → 配景点图）
                _ATTR_KW = (
                    r"古城|古镇|古村|老街|广场|公园|花园|植物园|动物园|游乐园|"
                    r"山|湖|海|滩|瀑|泉|潭|洞|谷|林|原|漠|关|岛|礁|湾|港|"
                    r"寺|庙|塔|阁|楼|台|殿|宫|观|庵|刹|院|祠|"
                    r"博物馆|纪念馆|故居|遗址|旧址|书院|会馆|民宅|大院|庄园|"
                    r"温泉|滑雪|漂流|栈道|索桥|滑道|过山车|摩天轮|"
                    r"石窟|石雕|壁画|石刻|造像|岩画|"
                    r"路|街|巷|坊|里|弄|胡同|十字|牌楼|牌坊|门|"
                    r"江|河|溪|渠|沟|涧|川|湖|潭|"
                    r"区|中心|度假区|风景区|自然保护区|国家公园|森林公园|地质公园|"
                    r"影院|剧院|音乐厅|体育馆|运动场|游泳馆|水族馆|海洋馆|"
                    r"码头|渡口|机场|火车站|汽车站|地铁|公交站|"
                    r"市场|商业街|美食街|小吃街|购物中心|商场|"
                    r"大学|学院|图书馆|科技馆|美术馆|艺术馆|"
                    r"寨|村|庄|镇|城|街|道|岛|洲|滩|坝|坪|坡|岭|峰|顶|崖|"
                    r"景点|景区|"
                    r"玉水寨|蓝月谷|木府|狮子山|万古楼|四方街|黑龙潭|束河|白沙"
                )
                _ATTR_KW_RE = re.compile(_ATTR_KW)

                # 美食关键词（命中 → 按美食搜图，不走景点白名单）
                _FOOD_KW = (
                    r"美食|小吃|餐厅|饭店|酒楼|菜馆|食堂|美食街|小吃街|美食城|"
                    r"烤鸭|火锅|烧烤|排档|串串|麻辣烫|农家乐|"
                    r"名菜|特色菜|招牌菜|菜|甜品|糕点|点心|茶馆|咖啡|"
                    r"面馆|面条|饺子|包子|粥|汤包|鸭子|鱼|虾|蟹"
                )
                _FOOD_KW_RE = re.compile(_FOOD_KW)

                # 黑名单：纯信息类标题不配图（住宿/费用/交通/天气/Day标题等）
                _SKIP_KW = (
                    r"酒店|客栈|民宿|宾馆|旅馆|推荐住|"
                    r"费用|预算|价格|多少钱|门票|票价|"
                    r"交通|出行|到达|离开|市内|公交|地铁|打车|"
                    r"住宿|"
                    r"天气|气温|穿衣|提示|注意|贴士|提醒|"
                    r"建议|攻略|方案|行程|总结|分析|推荐|盘点|合集|汇总|清单|"
                    r"出发|返程|"
                    r"购物|特产|手信|伴手礼|"
                    r"安全|健康|紧急|医疗|"
                    r"Day\s*\d|第[一二三四五六七八九十\d]天|第[一二三四五六七八九十\d]步"
                )
                _SKIP_KW_RE = re.compile(_SKIP_KW)

                seen_attr = set()   # 景点去重
                seen_food = set()   # 美食去重（与景点分开）
                pending = []        # (名称, 标题匹配位置, 类别)
                in_food_section = False  # 是否处于美食板块（如"## 美食推荐"之下）

                # 去重时剥离的通用后缀（景点+美食通用）
                _core_re = (
                    r"(景区|风景名胜区|风景区|公园|广场|博物馆|纪念馆|"
                    r"故居|遗址|旧址|书院|会馆|大院|庄园|寺|庙|塔|阁|楼|"
                    r"餐厅|饭店|酒楼|菜馆|美食街|小吃街|美食城)$"
                )

                # 逐个标题/列表项分类
                for _s, _e, _raw, level in segs:
                    raw = _raw
                    # 去掉时间括号 / 时间段 / 开头emoji / 结尾标点
                    raw = re.sub(r"\s*[（(][^)）]*[)）]\s*$", "", raw).strip()
                    raw = re.sub(r"\s*[（(]?\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}[)）]?\s*$", "", raw).strip()
                    raw = re.sub(r"^[^\u4e00-\u9fa5A-Za-z0-9]+", "", raw).strip()
                    raw = re.sub(r"[\s:：，,。.!！?？、]+$", "", raw).strip()
                    if not raw or len(raw) < 2:
                        continue
                    # 黑名单命中 → 跳过不配图；含美食词的板块标题
                    # （如"特色美食推荐"）本身不配图，但标记后续进入美食板块
                    if _SKIP_KW_RE.search(raw):
                        in_food_section = bool(_FOOD_KW_RE.search(raw))
                        continue
                    is_food = bool(_FOOD_KW_RE.search(raw))
                    if level == "##":
                        # 二级标题只作板块标志（如"## 美食推荐"），本身不配图
                        if is_food:
                            in_food_section = True
                        elif _ATTR_KW_RE.search(raw):
                            in_food_section = False
                        continue
                    # 美食板块继承：## 美食推荐 之下的无关键词小标题
                    # （具体菜名如"九转大肠""把子肉"）默认按美食处理
                    if not is_food and in_food_section and not _ATTR_KW_RE.search(raw):
                        is_food = True
                    # 维护板块状态：进入美食板块 / 被景点标题打断则退出
                    if is_food:
                        in_food_section = True
                    elif _ATTR_KW_RE.search(raw):
                        in_food_section = False
                    if not is_food and not _ATTR_KW_RE.search(raw):
                        continue
                    # 第4步：去重——去掉后缀比核心名，子串包含或相同视为同一地点
                    norm = raw.replace(" ", "").strip()
                    _norm_core = re.sub(_core_re, "", norm)
                    seen = seen_food if is_food else seen_attr
                    is_dup = False
                    for s in seen:
                        s_core = re.sub(_core_re, "", s)
                        if _norm_core in s or s_core in norm or _norm_core == s_core:
                            is_dup = True
                            break
                    if is_dup:
                        continue
                    seen.add(norm)
                    pending.append((raw, _e, "food" if is_food else "attr"))

                # ===== 诊断日志：识别到的小标题 =====
                print(
                    f"[WebChannel] 标题识别: "
                    f"共 {len(segs)} 个标题/列表项, "
                    f"入选 {len(pending)} 个"
                )
                for name, _p, cat in pending:
                    print(f"  - [{cat}] {name}")

                if not pending:
                    print(
                        "[WebChannel] 警告: 未识别到任何景点/美食标题，"
                        "请检查 Agent 输出是否用了 ### 小标题"
                    )

                # 第5步：并发搜图 + 插入
                if pending:
                    async def _search_img(name: str, cat: str):
                        dest = (request.destination or "").strip()
                        # 名称里已含目的地时不再重复拼接，避免"重庆重庆小面"这类查询
                        if dest and dest not in name:
                            q = f"{dest}{name}"
                        else:
                            q = name
                        # 美食搜索词加“美食”提高相关性（名字已含“美食”则不加）
                        if cat == "food" and "美食" not in name:
                            q += "美食"
                        print(
                            f"  [搜图] name={name} "
                            f"destination={request.destination!r} "
                            f"query={q!r}"
                        )
                        return await _fetch_attraction_image(q, "")

                    raws = await asyncio.gather(
                        *[_search_img(n, c) for n, _, c in pending],
                        return_exceptions=True,
                    )

                    # ===== 诊断日志 =====
                    ok_count = sum(
                        1 for r in raws
                        if not isinstance(r, Exception) and r
                    )
                    fail_count = len(raws) - ok_count
                    print(
                        f"[WebChannel] 图片诊断: "
                        f"pending={len(pending)} "
                        f"搜图成功={ok_count} "
                        f"搜图失败={fail_count}"
                    )
                    for (name, _m, cat), r in zip(pending, raws):
                        if isinstance(r, Exception):
                            print(
                                f"  ✗ [{cat}] {name} "
                                f"异常: {r}"
                            )
                        elif not r:
                            print(f"  ✗ [{cat}] {name} 返回空")
                        else:
                            print(f"  ✓ [{cat}] {name} -> {r[:80]}")

                    insertions = []  # (position, markdown_text)
                    for (name, end_pos, _cat), rurl in zip(pending, raws):
                        if isinstance(rurl, Exception) or not rurl:
                            continue
                        # 每个图 URL 包一层代理，彻底绕过防盗链
                        enc = urllib.parse.quote_plus(rurl, safe="")
                        proxy = f"http://127.0.0.1:{self.port}/proxy_img?remote_url=" + enc
                        safe_n = name.replace("]", "｜").replace("[", "（")
                        # 以 Markdown 图片行插到标题/列表项行的下一行
                        nl = result.find("\n", end_pos)
                        pos = nl if nl != -1 else len(result)
                        insertions.append((pos, "\n\n![" + safe_n + "](" + proxy + ")"))

                    # 从后往前插入（按位置倒序），保证前面的偏移不变
                    insertions.sort(key=lambda x: -x[0])
                    for pos, text in insertions:
                        result = result[:pos] + text + result[pos:]
            except Exception as _e:
                print("[WebChannel] 景点图片注入异常(不影响主流程): " + str(_e))

            # 返回纯 Markdown（图片语法 ![名称](代理URL) 交给前端 simpleMd2Html 渲染）
            # 不做 HTML 二次转换——后端转 HTML 会和前端渲染器冲突导致标签裸奔
            print(
                "[WebChannel] 旅游规划完成:"
                f" session_key={session_key}"
            )

            return {
                "success": True,
                "session_key": session_key,
                "destination": request.destination,
                "plan": result,
            }

    async def send(
        self,
        message: OutboundMessage,
    ) -> None:
        """发送消息到 WebSocket 客户端。

        Args:
            message: 出站消息实例
        """

        ws = self._connections.get(
            message.chat_id
        )

        if ws is None:
            print(
                "[WebChannel] 连接不存在:"
                f" chat_id={message.chat_id}"
            )
            return

        try:
            await ws.send_text(
                message.content
            )

            print(
                "[WebChannel] 消息已发送:"
                f" chat_id={message.chat_id}"
            )

        except Exception as e:
            print(
                "[WebChannel] 发送失败:"
                f" chat_id={message.chat_id}"
                f" reason={e}"
            )

            self._connections.pop(
                message.chat_id,
                None,
            )

    async def stop(self) -> None:
        """停止 Web 服务。"""

        if self._server is not None:
            self._server.should_exit = True
            self._server = None

        # 关闭所有 WebSocket
        for client_id, ws in list(
            self._connections.items()
        ):
            try:
                await ws.close()
            except Exception:
                pass

        self._connections.clear()

        # 清理 Agent 缓存
        self._agents.clear()

        print(
            "[WebChannel] 服务已停止"
        )