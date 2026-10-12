const menuButton = document.querySelector(".menu-btn");
const nav = document.querySelector("nav");
if (menuButton && nav) {
  menuButton.addEventListener("click", () => {
    const open = nav.classList.toggle("open");
    menuButton.setAttribute("aria-expanded", String(open));
  });
}

const toast = document.querySelector("#toast");
let toastTimer;
function showToast(message) {
  if (!toast) return;
  clearTimeout(toastTimer);
  toast.textContent = message;
  toast.classList.add("show");
  toastTimer = setTimeout(() => toast.classList.remove("show"), 1800);
}

setTimeout(() => {
  document.querySelectorAll(".flash").forEach(item => item.remove());
}, 2600);

 /* ==========================================================
* 语音转文字：给页面所有 textarea 输入框加麦克风按钮
* 链路：浏览器录音(WAV) → TravelFrog /voice2text → 硅基流动 ASR
* ========================================================== */
(function () {
	const VOICE_API = "http://127.0.0.1:8081/voice2text";   // TravelFrog 地址

	// 把 PCM 采样块编码成 16bit 单声道 WAV
	function encodeWAV(chunks, sampleRate) {
	let len = 0;
	chunks.forEach(c => len += c.length);
	const buf = new ArrayBuffer(44 + len * 2);
	const v = new DataView(buf);
	const wstr = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
	wstr(0, "RIFF"); v.setUint32(4, 36 + len * 2, true); wstr(8, "WAVE");
	wstr(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
	v.setUint32(24, sampleRate, true); v.setUint32(28, sampleRate * 2, true);
	v.setUint16(32, 2, true); v.setUint16(34, 16, true);
	wstr(36, "data"); v.setUint32(40, len * 2, true);
	let off = 44;
	chunks.forEach(c => {
		for (let i = 0; i < c.length; i++, off += 2) {
		const s = Math.max(-1, Math.min(1, c[i]));
		v.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
		}
	});
	return new Blob([buf], { type: "audio/wav" });
	}

	// 停止录音后：裁掉首尾静音 + 重采样到 16kHz 单声道再编码 WAV
	// （说话前后空白常占录音近一半时长，裁掉后上传与识别都明显更快；
	//   16kHz 体积再缩 3 倍）
	// 全程降级保护：任何浏览器不支持时退回原始采样率，保证功能永不失败
	function resampleAndEncode(chunks, srcRate) {
		const total = chunks.reduce((a, c) => a + c.length, 0);
		if (!total) return Promise.resolve(new Blob([new ArrayBuffer(44)], { type: "audio/wav" }));
		try {
			// 1) 拼接所有采样块
			const all = new Float32Array(total);
			let off = 0;
			chunks.forEach(c => { all.set(c, off); off += c.length; });

			// 2) 裁剪首尾静音（幅度低于 0.01 视为静音）
			const TH = 0.01;
			let s = 0, e = all.length;
			while (s < e && Math.abs(all[s]) < TH) s++;
			while (e > s && Math.abs(all[e - 1]) < TH) e--;
			// 有效语音不足 0.3 秒 → 视为没说话，返回空音频走"没听清"提示
			if (e - s < srcRate * 0.3) {
				return Promise.resolve(new Blob([new ArrayBuffer(44)], { type: "audio/wav" }));
			}
			// 保留前后 150ms 缓冲，防止切字
			const pad = Math.floor(srcRate * 0.15);
			s = Math.max(0, s - pad);
			e = Math.min(all.length, e + pad);
			const pcm = all.subarray(s, e);

			// 3) 重采样到 16kHz 单声道（体积缩小约 3 倍）
			const OC = window.OfflineAudioContext || window.webkitOfflineAudioContext;
			if (!OC) throw new Error("OfflineAudioContext 不可用");
			const Ctx = window.AudioContext || window.webkitAudioContext;
			const tmp = new Ctx();
			const buf = tmp.createBuffer(1, pcm.length, srcRate);
			buf.getChannelData(0).set(pcm);
			tmp.close().catch(() => {});
			const targetRate = 16000;
			const frames = Math.max(1, Math.ceil(pcm.length * targetRate / srcRate));
			const offCtx = new OC(1, frames, targetRate);
			const srcNode = offCtx.createBufferSource();
			srcNode.buffer = buf;
			srcNode.connect(offCtx.destination);
			srcNode.start();
			return offCtx.startRendering()
				.then(rendered => encodeWAV([rendered.getChannelData(0)], targetRate))
				.catch(() => Promise.resolve(encodeWAV([pcm], srcRate)));  // 渲染失败→裁剪后原始WAV
		} catch (e) {
			return Promise.resolve(encodeWAV(chunks, srcRate));  // 环境不支持→原始WAV
		}
	}

	// 全局同一时间只允许一个输入框在录音
	let active = null;

	function stopActive() {
	if (active) { active.stop(); active = null; }
	}

	function attachVoice(ta) {
	if (ta.dataset.voiceReady) return;
	ta.dataset.voiceReady = "1";

	// 包一层相对定位容器，麦克风按钮悬停在输入框右下角
	const wrap = document.createElement("span");
	wrap.style.cssText = "position:relative;display:block;";
	ta.parentNode.insertBefore(wrap, ta);
	wrap.appendChild(ta);

	const btn = document.createElement("button");
	btn.type = "button";
	btn.title = "点击说话，再次点击结束";
	btn.textContent = "🎤";
	btn.style.cssText = [
		"position:absolute", "right:10px", "bottom:10px", "z-index:5",
		"width:38px", "height:38px", "border-radius:50%",
		"border:1px solid #e0e0e0", "background:#fff", "cursor:pointer",
		"font-size:17px", "line-height:1", "box-shadow:0 2px 6px rgba(0,0,0,.12)",
		"transition:transform .15s ease"
	].join(";");
	wrap.appendChild(btn);

	let recorder = null; // {stop(): Promise<Blob>}

	async function start() {
		const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
		const Ctx = window.AudioContext || window.webkitAudioContext;
		const ctx = new Ctx();
		const srcNode = ctx.createMediaStreamSource(stream);
		const proc = ctx.createScriptProcessor(4096, 1, 1);
		const chunks = [];
		proc.onaudioprocess = e => chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
		srcNode.connect(proc);
		proc.connect(ctx.destination); // ScriptProcessor 必须连到 destination 才会触发
		const rate = ctx.sampleRate;
		btn.textContent = "⏹";
		btn.style.background = "#ffe9e9";
		btn.style.borderColor = "#e74c3c";
		btn.style.animation = "voicePulse 1.2s infinite";
		ta.placeholder = "正在录音，再点一次结束…";
		recorder = {
			stop() {
				return new Promise(resolve => {
					proc.disconnect(); srcNode.disconnect();
					stream.getTracks().forEach(t => t.stop());
					ctx.close().catch(() => {});
					resolve(resampleAndEncode(chunks, rate));
				});
			}
			};
	}

	function resetBtn() {
		btn.textContent = "🎤";
		btn.style.background = "#fff";
		btn.style.borderColor = "#e0e0e0";
		btn.style.animation = "";
		ta.placeholder = ta.dataset.voicePlaceholder || "";
	}

	async function recognize(blob) {
		// 65 秒超时：硅基流动免费 ASR 排队常达 20-45s，给足时间；
		// 超时立刻中断请求并恢复按钮
		const ctrl = new AbortController();
		const timer = setTimeout(() => ctrl.abort(), 65000);
		try {
			const resp = await fetch(VOICE_API, { method: "POST", body: blob, signal: ctrl.signal });
			const data = await resp.json().catch(() => ({ error: "服务返回异常" }));
			if (data.error) { showToast("语音识别失败：" + data.error); return; }
			const text = (data.text || "").trim();
			if (!text) { showToast("没听清你说的话，再试一次"); return; }
			// 插入到光标位置（无光标则追加到末尾）
			const st = ta.selectionStart ?? ta.value.length;
			const en = ta.selectionEnd ?? st;
			ta.value = ta.value.slice(0, st) + text + ta.value.slice(en);
			ta.selectionStart = ta.selectionEnd = st + text.length;
			ta.focus();
			ta.dispatchEvent(new Event("input", { bubbles: true }));
			showToast("语音已转为文字 ✅");
		}
		finally {
			clearTimeout(timer);
		}
	}

	btn.addEventListener("click", async () => {
		if (recorder) { // 停止 → 识别
		const r = recorder; recorder = null;
		if (active === r) active = null;
		resetBtn();
		// 识别中状态反馈：按钮转圈 + 输入框提示，避免"半天没反应"的观感
		btn.textContent = "⏳";
		btn.disabled = true;
		btn.style.opacity = "0.6";
		ta.placeholder = "识别中，语音接口响应较慢（约 10~40 秒），请稍候…";
		showToast("录音结束，正在识别，请稍候几秒…");
		try {
			// stop（重采样编码）与 recognize 全部包进 try，
			// 任何一步出错都不会卡死按钮
			const blob = await r.stop();
			await recognize(blob);
		}
		catch (e) {
			const msg = (e && e.name === "AbortError") ? "识别超时，请重试" : (e && e.message) || "未知错误";
			showToast("语音识别失败：" + msg);
		}
		finally {
			// 无论成功失败都恢复按钮，杜绝"变灰点不了"
			btn.disabled = false;
			btn.style.opacity = "";
			btn.textContent = "🎤";
			ta.placeholder = ta.dataset.voicePlaceholder || "";
		}
		return;
		}
		// 开始录音
		if (active) { stopActive(); }
		if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
		showToast("当前浏览器不支持录音（请用 Edge/Chrome，且通过 localhost 访问）");
		return;
		}
		try {
		if (!ta.dataset.voicePlaceholder) ta.dataset.voicePlaceholder = ta.placeholder;
		await start();
		active = recorder;
		} catch (e) {
		resetBtn();
		showToast("无法访问麦克风：" + e.message);
		}
	});

	// 按钮脉冲动画样式（只注入一次）
	if (!document.getElementById("voice-pulse-style")) {
		const st = document.createElement("style");
		st.id = "voice-pulse-style";
		st.textContent = "@keyframes voicePulse{0%{box-shadow:0 0 0 0 rgba(231,76,60,.45)}70%{box-shadow:0 0 0 12px rgba(231,76,60,0)}100%{box-shadow:0 0 0 0 rgba(231,76,60,0)}}";
		document.head.appendChild(st);
	}
	}

	function initVoice() {
	document.querySelectorAll("textarea").forEach(ta => {
		if (!ta.readOnly && !ta.disabled) attachVoice(ta);
	});
	}
	if (document.readyState === "loading") {
	document.addEventListener("DOMContentLoaded", initVoice);
	} else {
	initVoice();
	}
})();
