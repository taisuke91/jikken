(() => {
  const $ = (id) => document.getElementById(id);

  const btnRecord = $("btnRecord");
  const recStatus = $("recStatus");
  const scoreNum = $("scoreNum");
  const scoreLabel = $("scoreLabel");
  const barFill = $("barFill");
  const rawOut = $("rawOut");
  const manualGrid = $("manualGrid");
  const manualStatus = $("manualStatus");
  const appMain = $("appMain");
  const flareCallout = $("flareCallout");
  const flareCalloutText = $("flareCalloutText");
  const recLevelWrap = $("recLevelWrap");
  const recLevelFill = $("recLevelFill");
  const recLevelTrack = $("recLevelTrack");
  const recWaveform = $("recWaveform");

  let inputMeterCtx = null;
  let inputMeterRaf = null;
  let inputMeterSmooth = 0;

  const FLARE_COPY = {
    1: "火種が見えています。言い過ぎや誤解を招く表現がないか見直し、必要なら一言謝罪や言い換えを検討しましょう。",
    2: "かなり燃えやすい状態です。謝罪や説明・トーンを落とした言い換えを早めに入れた方がよさそうです。",
    3: "いまは強い炎上リスクです。早めの謝罪と事実関係の整理がないと収束が難しくなりがちです。",
  };

  function updateFlareUi(state) {
    if (!appMain || !flareCallout || !flareCalloutText) return;
    const heat =
      typeof state === "number" && !Number.isNaN(state)
        ? Math.max(0, Math.min(3, Math.floor(state)))
        : 0;
    appMain.dataset.heat = String(heat);
    if (heat >= 1 && heat <= 3) {
      flareCallout.classList.remove("flare-callout--hide");
      flareCallout.setAttribute("aria-hidden", "false");
      flareCalloutText.textContent = FLARE_COPY[heat];
    } else {
      flareCallout.classList.add("flare-callout--hide");
      flareCallout.setAttribute("aria-hidden", "true");
      flareCalloutText.textContent = "";
    }
  }

  function setMeter(state, label, raw) {
    if (typeof state !== "number" || Number.isNaN(state)) {
      scoreNum.textContent = "—";
      scoreLabel.textContent = label || "エラー";
      barFill.style.width = "0%";
      updateFlareUi(NaN);
    } else {
      scoreNum.textContent = String(state);
      scoreLabel.textContent = label || "";
      barFill.style.width = `${Math.min(100, Math.max(0, (state / 3) * 100))}%`;
      updateFlareUi(state);
    }
    if (raw !== undefined) {
      rawOut.textContent =
        typeof raw === "string" ? raw : JSON.stringify(raw, null, 2);
    }
  }

  async function postJson(path, body) {
    const url = path;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const text = await res.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
    if (!res.ok) {
      const msg = data.detail || text || res.statusText;
      throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
    return data;
  }

  async function postAudio(blob) {
    const fd = new FormData();
    fd.append("file", blob, "recording.webm");
    const url = "/api/score-audio";
    console.info("[score-audio] 送信", {
      blobSize: blob.size,
      blobType: blob.type,
    });
    if (blob.size === 0) {
      console.warn("[score-audio] 録音バイト数が 0 — MediaRecorder のデータが来ていない可能性");
    }
    const res = await fetch(url, { method: "POST", body: fd });
    const text = await res.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
    if (!res.ok) {
      console.error("[score-audio] 失敗", {
        status: res.status,
        statusText: res.statusText,
        bodyPreview: text.slice(0, 800),
        detail: data.detail,
      });
      const msg = data.detail || text || res.statusText;
      throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
    console.info("[score-audio] 成功", {
      state: data.state,
      score: data.score,
      label: data.label,
    });
    return data;
  }

  function stopInputLevelMeter() {
    if (inputMeterRaf !== null) {
      cancelAnimationFrame(inputMeterRaf);
      inputMeterRaf = null;
    }
    inputMeterSmooth = 0;
    if (inputMeterCtx) {
      inputMeterCtx.close().catch(() => {});
      inputMeterCtx = null;
    }
    if (recLevelWrap) {
      recLevelWrap.classList.add("rec-level-wrap--hide");
      recLevelWrap.setAttribute("aria-hidden", "true");
    }
    if (recLevelFill) recLevelFill.style.width = "0%";
    if (recLevelTrack) recLevelTrack.setAttribute("aria-valuenow", "0");
    clearWaveformCanvas();
  }

  function clearWaveformCanvas() {
    const canvas = recWaveform;
    if (!canvas) return;
    const g = canvas.getContext("2d");
    if (!g) return;
    g.clearRect(0, 0, canvas.width, canvas.height);
  }

  /** マイクチェック風：タイムドメイン波形を 1 フレーム描画 */
  function drawWaveform(timeDomainBuf) {
    const canvas = recWaveform;
    if (!canvas) return;
    const g = canvas.getContext("2d");
    if (!g) return;
    const dpr = window.devicePixelRatio || 1;
    const cssW = Math.max(
      160,
      canvas.clientWidth ||
        canvas.offsetWidth ||
        (recLevelWrap && recLevelWrap.clientWidth) ||
        320
    );
    const cssH = Math.max(48, canvas.clientHeight || canvas.offsetHeight || 56);
    const bufW = Math.floor(cssW * dpr);
    const bufH = Math.floor(cssH * dpr);
    if (canvas.width !== bufW || canvas.height !== bufH) {
      canvas.width = bufW;
      canvas.height = bufH;
    }
    const w = bufW;
    const h = bufH;
    g.fillStyle = "#2a2420";
    g.fillRect(0, 0, w, h);
    g.strokeStyle = "rgba(235, 200, 168, 0.22)";
    g.lineWidth = dpr;
    g.beginPath();
    g.moveTo(0, h / 2);
    g.lineTo(w, h / 2);
    g.stroke();
    const len = timeDomainBuf.length;
    const amp = h * 0.42;
    const mid = h / 2;
    const step = w / Math.max(1, len - 1);
    g.strokeStyle = "#e89548";
    g.lineWidth = 2 * dpr;
    g.lineCap = "round";
    g.lineJoin = "round";
    g.shadowColor = "rgba(200, 95, 52, 0.42)";
    g.shadowBlur = 4 * dpr;
    g.beginPath();
    for (let i = 0; i < len; i++) {
      const v = (timeDomainBuf[i] - 128) / 128;
      const x = i * step;
      const y = mid - v * amp;
      if (i === 0) g.moveTo(x, y);
      else g.lineTo(x, y);
    }
    g.stroke();
    g.shadowBlur = 0;
  }

  function runInputMeterLoop(analyser, timeDomainBuf) {
    analyser.getByteTimeDomainData(timeDomainBuf);
    drawWaveform(timeDomainBuf);
    let sum = 0;
    for (let i = 0; i < timeDomainBuf.length; i++) {
      const x = (timeDomainBuf[i] - 128) / 128;
      sum += x * x;
    }
    const rms = Math.sqrt(sum / timeDomainBuf.length);
    const amplified = Math.min(1, rms * 5.5);
    inputMeterSmooth = inputMeterSmooth * 0.78 + amplified * 0.22;
    const pct = Math.min(100, Math.max(0, Math.round(inputMeterSmooth * 100)));
    if (recLevelFill) recLevelFill.style.width = `${pct}%`;
    if (recLevelTrack) recLevelTrack.setAttribute("aria-valuenow", String(pct));
    inputMeterRaf = requestAnimationFrame(() =>
      runInputMeterLoop(analyser, timeDomainBuf)
    );
  }

  async function startInputLevelMeter(stream) {
    stopInputLevelMeter();
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC || !stream || !recLevelWrap || !recLevelFill) return;
    const ctx = new AC();
    try {
      await ctx.resume();
    } catch (_) {
      /* Safari がユーザー操作直後以外で suspend している場合など */
    }
    const src = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    analyser.smoothingTimeConstant = 0.45;
    src.connect(analyser);
    inputMeterCtx = ctx;
    recLevelWrap.classList.remove("rec-level-wrap--hide");
    recLevelWrap.setAttribute("aria-hidden", "false");
    const timeDomainBuf = new Uint8Array(analyser.fftSize);
    inputMeterRaf = requestAnimationFrame(() =>
      runInputMeterLoop(analyser, timeDomainBuf)
    );
  }

  let mediaRecorder = null;
  let chunks = [];

  btnRecord.addEventListener("click", async () => {
    if (mediaRecorder && mediaRecorder.state === "recording") {
      mediaRecorder.stop();
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunks = [];
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      mediaRecorder = new MediaRecorder(stream, { mimeType: mime });
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data);
      };
      mediaRecorder.onstop = async () => {
        stopInputLevelMeter();
        stream.getTracks().forEach((t) => t.stop());
        recStatus.textContent = "送信中…";
        btnRecord.textContent = "録音して判定";
        const blob = new Blob(chunks, { type: mime });
        const chunkCount = chunks.length;
        const approxChunkBytes = chunks.reduce((n, c) => n + c.size, 0);
        console.info("[record] 録音停止", {
          chunkCount,
          approxChunkBytes,
          blobSize: blob.size,
          mime,
        });
        if (chunkCount === 0 || blob.size === 0) {
          console.warn(
            "[record] チャンクが空、またはバイト 0。短すぎる録音やブラウザ差の疑い。もう少し長く録音してみてください。"
          );
        }
        try {
          const data = await postAudio(blob);
          setMeter(data.state, data.label, data);
          recStatus.textContent = "完了";
        } catch (e) {
          console.error(e);
          setMeter(null, "送信失敗", String(e.message || e));
          recStatus.textContent = "エラー";
        }
      };
      mediaRecorder.start();
      await startInputLevelMeter(stream);
      recStatus.textContent = "録音中（もう一度タップで送信）";
      btnRecord.textContent = "送信";
    } catch (e) {
      console.error(e);
      stopInputLevelMeter();
      setMeter(null, "マイク使用不可", String(e.message || e));
      recStatus.textContent = "マイク許可を確認してください";
    }
  });

  /**手動 → マイコン（/api/mcu-push） */
  if (manualGrid) {
    for (let n = 0; n <= 3; n++) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = String(n);
      b.title = `状態 ${n} を送信`;
      b.addEventListener("click", async () => {
        manualStatus.textContent = "送信中…";
        try {
          const data = await postJson("/api/mcu-push", { state: n });
          const ok = data.serial_write_ok;
          const cfg = data.serial_configured;
          manualStatus.textContent = cfg
            ? ok
              ? `送信 OK（状態 ${n}）`
              : "シリアル書き込み失敗（他アプリがポート使用中かも）"
            : "SERIAL_PORT 未設定（.env を確認）";
          setMeter(data.state, data.label, {
            mode: "mcu-push",
            ...data,
          });
        } catch (e) {
          console.error(e);
          manualStatus.textContent = `エラー: ${e.message || e}`;
          setMeter(null, "送信失敗", String(e.message || e));
        }
      });
      manualGrid.appendChild(b);
    }
  }

  updateFlareUi(undefined);
})();
