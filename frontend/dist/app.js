(() => {
  const $ = (id) => document.getElementById(id);

  const btnRecord = $("btnRecord");
  const btnSpeech = $("btnSpeech");
  const recStatus = $("recStatus");
  const scoreNum = $("scoreNum");
  const scoreLabel = $("scoreLabel");
  const barFill = $("barFill");
  const rawOut = $("rawOut");
  const manualGrid = $("manualGrid");
  const manualStatus = $("manualStatus");

  function setMeter(score, label, raw) {
    if (typeof score !== "number" || Number.isNaN(score)) {
      scoreNum.textContent = "—";
      scoreLabel.textContent = label || "エラー";
      barFill.style.width = "0%";
    } else {
      scoreNum.textContent = String(score);
      scoreLabel.textContent = label || "";
      barFill.style.width = `${Math.min(100, Math.max(0, (score / 10) * 100))}%`;
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
    const res = await fetch(url, { method: "POST", body: fd });
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
        stream.getTracks().forEach((t) => t.stop());
        recStatus.textContent = "送信中…";
        btnRecord.textContent = "録音して判定（音声を API へ）";
        const blob = new Blob(chunks, { type: mime });
        try {
          const data = await postAudio(blob);
          setMeter(data.score, data.label, data);
          recStatus.textContent = "完了";
        } catch (e) {
          console.error(e);
          setMeter(null, "送信失敗", String(e.message || e));
          recStatus.textContent = "エラー";
        }
      };
      mediaRecorder.start();
      recStatus.textContent = "録音中…（もう一度ボタンで終了）";
      btnRecord.textContent = "録音終了して送信";
    } catch (e) {
      console.error(e);
      setMeter(null, "マイク使用不可", String(e.message || e));
      recStatus.textContent = "マイク許可を確認してください";
    }
  });

  btnSpeech.addEventListener("click", () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      setMeter(
        null,
        "非対応ブラウザ",
        "Web Speech API がありません（Chrome 推奨）"
      );
      return;
    }
    const rec = new SR();
    rec.lang = "ja-JP";
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    recStatus.textContent = "聞き取り中…話してください";
    rec.onresult = async (ev) => {
      const text = ev.results[0][0].transcript;
      recStatus.textContent = "判定中…";
      try {
        const data = await postJson("/api/score-text", { transcript: text });
        setMeter(data.score, data.label, { ...data, transcript: text });
        recStatus.textContent = "完了";
      } catch (e) {
        console.error(e);
        setMeter(null, "APIエラー", String(e.message || e));
        recStatus.textContent = "エラー";
      }
    };
    rec.onerror = (ev) => {
      setMeter(null, "音声認識エラー", ev.error || "error");
      recStatus.textContent = "エラー";
    };
    rec.start();
  });

  /**手動 → マイコン（/api/mcu-push） */
  if (manualGrid) {
    for (let n = 1; n <= 10; n++) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = String(n);
      b.title = `スコア ${n} を送信`;
      b.addEventListener("click", async () => {
        manualStatus.textContent = "送信中…";
        try {
          const data = await postJson("/api/mcu-push", { score: n });
          const ok = data.serial_write_ok;
          const cfg = data.serial_configured;
          manualStatus.textContent = cfg
            ? ok
              ? `送信 OK（${n}）`
              : "シリアル書き込み失敗（他アプリがポート使用中かも）"
            : "SERIAL_PORT 未設定（.env を確認）";
          setMeter(data.score, data.label, {
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
})();
