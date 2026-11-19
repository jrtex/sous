(() => {
  const { sessionId, steps } = window.SOUS;
  const $ = (id) => document.getElementById(id);
  const storeKey = `sous:step:${sessionId}`;

  // ---- Step navigation (the UI owns the current step) ----
  let current = 1;
  try { current = Math.min(Math.max(1, Number(sessionStorage.getItem(storeKey)) || 1), steps.length); } catch {}

  function render() {
    const s = steps[current - 1];
    if (!s) return;
    $("counter").textContent = `Step ${current} / ${steps.length}`;
    $("section").textContent = s.section || "";
    $("step-text").textContent = s.text;
    $("step-ingredients").replaceChildren(...s.ingredients.map((t) => {
      const li = document.createElement("li"); li.textContent = t; return li;
    }));
    $("step-timers").replaceChildren(...s.timers.map((t) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = `⏱ ${t.label}`;
      b.onclick = () => startTimer(`Step ${current}: ${t.label}`, t.seconds);
      return b;
    }));
    $("prev").disabled = current === 1;
    $("next").textContent = current === steps.length ? "Done" : "Next";
    $("next").disabled = current === steps.length;
    try { sessionStorage.setItem(storeKey, String(current)); } catch {}
  }
  $("prev").onclick = () => { current = Math.max(1, current - 1); render(); };
  $("next").onclick = () => { current = Math.min(steps.length, current + 1); render(); };

  // ---- Timers ----
  let audio;
  function beep() {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      const o = audio.createOscillator(), g = audio.createGain();
      o.frequency.value = 880; g.gain.value = 0.2;
      o.connect(g); g.connect(audio.destination);
      o.start(); o.stop(audio.currentTime + 0.4);
    } catch {}
  }
  const fmt = (s) => {
    s = Math.max(0, Math.ceil(s));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return (h ? `${h}:${String(m).padStart(2, "0")}` : `${m}`) + `:${String(sec).padStart(2, "0")}`;
  };

  function startTimer(label, seconds) {
    // Unlock audio on the user's tap so the alarm can play later.
    try { audio = audio || new (window.AudioContext || window.webkitAudioContext)(); audio.resume(); } catch {}
    const end = Date.now() + seconds * 1000;
    const el = document.createElement("div");
    el.className = "timer";
    el.innerHTML = `<div><div class="t-left"></div><div class="t-label"></div></div><button type="button">✕</button>`;
    el.querySelector(".t-label").textContent = label;
    const left = el.querySelector(".t-left");
    let ring;
    const tick = setInterval(() => {
      const rem = (end - Date.now()) / 1000;
      left.textContent = fmt(rem);
      if (rem <= 0 && !ring) {
        el.classList.add("ringing");
        left.textContent = "Done!";
        beep(); try { navigator.vibrate?.([400, 200, 400]); } catch {}
        ring = setInterval(() => { beep(); }, 1500);
      }
    }, 250);
    el.querySelector("button").onclick = () => {
      clearInterval(tick); clearInterval(ring); el.remove();
      $("timers").hidden = !$("timers").children.length;
    };
    left.textContent = fmt(seconds);
    $("timers").append(el);
    $("timers").hidden = false;
  }

  // ---- Keep the screen awake while cooking ----
  async function wake() { try { await navigator.wakeLock?.request("screen"); } catch {} }
  wake();
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") wake(); });

  // ---- Chat ----
  const log = $("log");
  function addMsg(role, text) {
    const li = document.createElement("li");
    li.className = `msg ${role}`;
    li.textContent = text;
    log.append(li);
    log.scrollTop = log.scrollHeight;
    return li;
  }
  log.scrollTop = log.scrollHeight;

  $("ask").onsubmit = async (e) => {
    e.preventDefault();
    const q = $("q").value.trim();
    if (!q) return;
    $("q").value = "";
    addMsg("user", q);
    const pending = addMsg("assistant pending", "…");
    try {
      const r = await fetch(`/api/s/${sessionId}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step: current, question: q }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || `Error ${r.status}`);
      pending.className = "msg assistant";
      pending.textContent = data.answer;
    } catch (err) {
      pending.className = "msg assistant error";
      pending.textContent = err.message;
    }
    log.scrollTop = log.scrollHeight;
  };

  render();
})();
