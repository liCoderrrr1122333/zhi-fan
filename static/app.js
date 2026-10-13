const $ = (sel) => document.querySelector(sel);
const api = async (url, opts) => (await fetch(url, opts)).json();
const post = (url, body) =>
  api(url, { method: "POST", headers: { "Content-Type": "application/json" },
             body: body ? JSON.stringify(body) : undefined });
const put = (url, body) =>
  api(url, { method: "PUT", headers: { "Content-Type": "application/json" },
             body: JSON.stringify(body) });
const del = (url) => api(url, { method: "DELETE" });

const SESSION = "demo";
const QUICK = [
  "有哪些课程?",
  "这个课多少钱?",
  "我零基础能学吗?",
  "太贵了,能便宜点吗?",
  "学完能找到工作吗?",
];

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function sourceLabel(source) {
  if (source === "ticket") return "工单补充";
  if (source === "refine") return "实测纠偏";
  return "主动录入";
}

const TRAIN_SOURCES = "taught,ticket";
const REFINE_SOURCES = "refine";

// ---------- Tab 切换 ----------
document.querySelectorAll(".tab").forEach((t) => {
  t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    $("#tab-" + t.dataset.tab).classList.add("active");
    if (t.dataset.tab === "review") loadReview();
    refreshMetrics();
  });
});

// ---------- 策略沉淀模式开关 ----------
async function resetChat() {
  await post("/api/session/reset?session_id=" + SESSION);
  $("#messages").innerHTML = "";
  renderTrace([]);
}

$("#teach-toggle").addEventListener("change", async (e) => {
  const on = e.target.checked;
  $("#teach-box").classList.toggle("show", on);
  $("#ask-box").classList.toggle("hidden", on);
  $("#mode-hint").textContent = on
    ? "录入一条策略：客户会怎么问、这时该怎么说、为什么这么说。"
    : "模拟客户提问，观察人工智能如何按策略判断。";
  // 切换模式=开始一段全新测试:清掉旧上下文,并让最新总纲/设定生效
  await resetChat();
  if (on) loadTaught();
});

// 策略沉淀模式里只展示主动样本(不含纠错固化)
async function loadTaught() {
  const list = await api("/api/playbook?source=" + encodeURIComponent(TRAIN_SOURCES));
  $("#taught-count").textContent = list.length;
  const box = $("#taught-list");
  box.innerHTML = list.length ? "" : '<div class="empty">还没有保存过策略。</div>';
  list.forEach((k) => {
    const el = document.createElement("div");
    el.className = "taught-item";
    el.innerHTML = `<div class="tq">${escapeHtml(k.question)}</div>` +
      (k.note ? `<div class="tn">原因：${escapeHtml(k.note)}</div>` : "") +
      `<div class="tn">${sourceLabel(k.source)}</div>`;
    box.appendChild(el);
  });
}

// ---------- 聊天 ----------
function addMessage(text, who, handoff) {
  const div = document.createElement("div");
  div.className = "msg " + who + (handoff ? " handoff" : "");
  div.textContent = text;
  $("#messages").appendChild(div);
  $("#messages").scrollTop = $("#messages").scrollHeight;
}

// AI 回复(带「纠偏 / 固化」能力)。question=触发这条回复的客户问题。
function addBotMessage(text, opts = {}) {
  const { handoff = false, question = null, revised = false, feedback = "" } = opts;
  const wrap = document.createElement("div");
  wrap.className = "msg bot" + (handoff ? " handoff" : "");

  if (revised) {
    const badge = document.createElement("div");
    badge.className = "revised-badge";
    badge.textContent = "↻ 已按你的意见修正";
    wrap.appendChild(badge);
  }
  const content = document.createElement("div");
  content.textContent = text;
  wrap.appendChild(content);

  if (!handoff && question) {
    const bar = document.createElement("div");
    bar.className = "msg-actions";

    const refineBtn = document.createElement("button");
    refineBtn.className = "mini-btn";
    refineBtn.textContent = "纠偏";
    refineBtn.onclick = () => openRefineBox(wrap, question, text);
    bar.appendChild(refineBtn);

    if (revised) {
      const commitBtn = document.createElement("button");
      commitBtn.className = "mini-btn ok";
      commitBtn.textContent = "保存到策略库";
      commitBtn.onclick = async () => {
        commitBtn.disabled = true;
        commitBtn.textContent = "正在保存…";
        await post("/api/refine/commit", { question, answer: text, feedback });
        commitBtn.textContent = "已保存";
        refreshMetrics();
        // 纠偏固化进「纠偏数据」,不刷新策略样本清单
      };
      bar.appendChild(commitBtn);
    }
    wrap.appendChild(bar);
  }

  $("#messages").appendChild(wrap);
  $("#messages").scrollTop = $("#messages").scrollHeight;
}

function openRefineBox(wrap, question, reply) {
  if (wrap.querySelector(".refine-box")) return;
  const box = document.createElement("div");
  box.className = "refine-box";
  const ta = document.createElement("textarea");
  ta.placeholder = "说说这条哪里不对、该往哪改…例如:别急着给案例,先问预算";
  const btns = document.createElement("div");
  btns.className = "refine-btns";
  const submit = document.createElement("button");
  submit.className = "mini-btn ok";
  submit.textContent = "提交纠偏";
  const cancel = document.createElement("button");
  cancel.className = "mini-btn";
  cancel.textContent = "取消";
  cancel.onclick = () => box.remove();
  submit.onclick = async () => {
    const fb = ta.value.trim();
    if (!fb) return;
    submit.disabled = true;
    submit.textContent = "正在重新生成…";
    const r = await post("/api/refine",
      { question, reply, feedback: fb, session_id: SESSION });
    box.remove();
    addBotMessage(r.reply, { question, revised: true, feedback: fb });
  };
  btns.appendChild(submit);
  btns.appendChild(cancel);
  box.appendChild(ta);
  box.appendChild(btns);
  wrap.appendChild(box);
  ta.focus();
}

// 把一条内部 message 渲染成便于调试阅读的摘要行
function fmtMessage(m) {
  const role = m.role || "?";
  if (role === "assistant" && Array.isArray(m.tool_calls) && m.tool_calls.length) {
    const calls = m.tool_calls
      .map((c) => `${c.name}(${JSON.stringify(c.input || {})})`)
      .join(", ");
    const th = m.content ? ` 「${m.content}」` : "";
    return `[assistant → 调用]${th} ${calls}`;
  }
  if (role === "tool") {
    return `[tool:${m.name}] ${JSON.stringify(m.result)}`;
  }
  return `[${role}] ${m.content || ""}`;
}

function renderTrace(trace) {
  const box = $("#trace");
  box.innerHTML = "";
  if (!trace || !trace.length) {
    box.innerHTML = '<div class="trace-empty">无轨迹</div>';
    return;
  }
  const labels = {
    llm_call: "🧠 LLM 调用(上下文)",
    llm_response: "🧠 LLM 决策",
    think: "💭 思考",
    tool_call: "🔧 调用工具",
    tool_result: "📦 工具结果",
    final: "✅ 最终回复",
  };
  trace.forEach((s) => {
    const el = document.createElement("div");
    let cls = "tstep " + s.type;
    if (s.type === "tool_result" && s.is_error) cls += " error";
    el.className = cls;

    let inner = `<div class="k">第${s.step}步 · ${labels[s.type] || s.type}${s.tool ? " · " + s.tool : ""}</div>`;

    // ① LLM 调用:展示可用工具 + 可折叠的完整上下文(喂给模型的 messages)
    if (s.type === "llm_call") {
      if (s.available_tools) {
        inner += `<div class="sub">可用工具:${escapeHtml(s.available_tools.join(", "))}</div>`;
      }
      const msgs = s.messages || [];
      const lines = msgs.map((m) => escapeHtml(fmtMessage(m))).join("\n");
      inner += `<details><summary>查看完整上下文(${msgs.length} 条消息)</summary><pre>${lines}</pre></details>`;
    }

    // ② LLM 决策:展示模型这一步决定"调工具"还是"直接回复"
    if (s.type === "llm_response") {
      if (s.decision === "tool_call" && s.tool_calls && s.tool_calls.length) {
        const names = s.tool_calls.map((c) => c.name).join(", ");
        inner += `<div class="sub">决策:调用工具 → ${escapeHtml(names)}${s.tool_calls.length > 1 ? "(并行)" : ""}</div>`;
        inner += `<pre>tool_calls ${escapeHtml(JSON.stringify(s.tool_calls))}</pre>`;
      } else {
        inner += `<div class="sub">决策:直接回复(结束循环)</div>`;
        if (s.content) inner += `<pre>${escapeHtml(s.content)}</pre>`;
      }
    }

    if (s.type !== "llm_call" && s.type !== "llm_response" && s.content) {
      inner += `<div>${escapeHtml(s.content)}</div>`;
    }
    if (s.input) inner += `<pre>入参 ${escapeHtml(JSON.stringify(s.input))}</pre>`;
    if (s.output) {
      inner += `<pre>出参 ${escapeHtml(JSON.stringify(s.output))}</pre>`;
      if (s.is_error) inner += `<div class="err-hint">⚠️ 工具返回错误 → 智能体会据此调整下一步</div>`;
    }
    el.innerHTML = inner;
    box.appendChild(el);
  });
}

async function send() {
  const input = $("#input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  addMessage(text, "user");
  renderTrace([{ step: 0, type: "think", content: "正在分析当前问题……" }]);
  const res = await post("/api/chat", { message: text, session_id: SESSION });
  addBotMessage(res.reply, { handoff: res.handoff, question: text });
  renderTrace(res.trace);
  refreshMetrics();
}

$("#send").addEventListener("click", send);
$("#input").addEventListener("keydown", (e) => { if (e.key === "Enter") send(); });
$("#reset").addEventListener("click", resetChat);

// ---------- 策略沉淀提交 ----------
$("#teach-btn").addEventListener("click", async () => {
  const question = $("#t-question").value.trim();
  const answer = $("#t-answer").value.trim();
  const note = $("#t-note").value.trim();
  if (!question || !answer) return alert("请至少填写「客户问题」和「标准答案」");
  await post("/api/teach", { question, answer, note });
  addMessage(`已保存策略：「${question}」`, "bot");
  $("#t-question").value = ""; $("#t-answer").value = ""; $("#t-note").value = "";
  refreshMetrics();
  loadTaught();
});

// 快捷问句
const quickBox = $("#quick");
QUICK.forEach((q) => {
  const b = document.createElement("button");
  b.textContent = q;
  b.onclick = () => {
    if ($("#teach-toggle").checked) { $("#t-question").value = q; return; }
    $("#input").value = q; send();
  };
  quickBox.appendChild(b);
});

// ---------- 指标 ----------
async function refreshMetrics() {
  const m = await api("/api/metrics");
  $("#m-taught").textContent = m.taught_count ?? m.kb_count ?? 0;
  $("#m-refine").textContent = m.refine_count ?? 0;
  $("#m-chats").textContent = m.total_chats;
  $("#m-handoff").textContent = (m.handoff_rate * 100).toFixed(0) + "%";
  $("#m-hit").textContent = (m.kb_hit_rate * 100).toFixed(0) + "%";
}

// ---------- 样本快速查看(训练 / 纠错分开展示) ----------
async function openKbModal(kind) {
  const isRefine = kind === "refine";
  const source = isRefine ? REFINE_SOURCES : TRAIN_SOURCES;
  $("#kb-modal-title").textContent = isRefine ? "纠偏固化" : "策略样本";
  const list = await api("/api/playbook?source=" + encodeURIComponent(source));
  const box = $("#kb-list");
  const empty = isRefine
    ? '<div class="empty">还没有纠偏记录。在对话里点「纠偏」，认可后再保存到策略库。</div>'
    : '<div class="empty">策略库还是空的。打开「沉淀策略」写第一条。</div>';
  box.innerHTML = list.length ? "" : empty;
  list.forEach((k) => {
    const c = document.createElement("div");
    c.className = "kb-item";
    c.innerHTML = `
      <div class="q">${escapeHtml(k.question)}</div>
      <div class="answer-box">${escapeHtml(k.answer)}</div>
      ${k.note ? `<div class="note-box">原因：${escapeHtml(k.note)}</div>` : ""}
      <div class="meta">#${k.id} · ${sourceLabel(k.source)} · ${escapeHtml(k.created_at || "")}</div>`;
    box.appendChild(c);
  });
  $("#kb-modal").classList.add("show");
}
$("#m-taught-card").addEventListener("click", () => openKbModal("taught"));
$("#m-refine-card").addEventListener("click", () => openKbModal("refine"));
$("#kb-close").addEventListener("click", () => $("#kb-modal").classList.remove("show"));
$("#kb-modal").addEventListener("click", (e) => {
  if (e.target.id === "kb-modal") $("#kb-modal").classList.remove("show");
});

// ---------- 自动归纳的策略总纲 ----------
$("#summary-btn").addEventListener("click", async () => {
  $("#sum-text").value = "";
  $("#sum-text").placeholder = "正在整理策略总纲……";
  $("#sum-status").textContent = "";
  $("#sum-modal").classList.add("show");
  const r = await api("/api/playbook/summary");
  $("#sum-text").value = r.summary || "";
});
$("#sum-save").addEventListener("click", async () => {
  await put("/api/playbook/summary", { text: $("#sum-text").value });
  $("#sum-status").textContent = "已保存 ✓";
  setTimeout(() => ($("#sum-status").textContent = ""), 1500);
});
$("#sum-regen").addEventListener("click", async () => {
  $("#sum-status").textContent = "AI 正在合并归纳(保留你的改写)……";
  const r = await post("/api/playbook/summary/regenerate");
  $("#sum-text").value = r.summary || "";
  $("#sum-status").textContent = "已重新归纳 ✓";
  setTimeout(() => ($("#sum-status").textContent = ""), 1500);
});
$("#sum-close").addEventListener("click", () => $("#sum-modal").classList.remove("show"));
$("#sum-modal").addEventListener("click", (e) => {
  if (e.target.id === "sum-modal") $("#sum-modal").classList.remove("show");
});

// ---------- 完整系统提示词(只读) ----------
$("#prompt-btn").addEventListener("click", async () => {
  $("#prompt-text").textContent = "加载中……";
  $("#prompt-modal").classList.add("show");
  const r = await api("/api/settings/system-prompt");
  $("#prompt-text").textContent = r.prompt || "(无内容)";
});
$("#prompt-close").addEventListener("click", () => $("#prompt-modal").classList.remove("show"));
$("#prompt-modal").addEventListener("click", (e) => {
  if (e.target.id === "prompt-modal") $("#prompt-modal").classList.remove("show");
});

// ---------- AI 业务设定 ----------
async function loadDirective() {
  const r = await api("/api/settings/directive");
  $("#directive").value = r.directive || "";
}
$("#save-directive").addEventListener("click", async () => {
  const btn = $("#save-directive");
  await put("/api/settings/directive", { text: $("#directive").value });
  const old = btn.textContent;
  btn.textContent = "已保存 ✓";
  setTimeout(() => (btn.textContent = old), 1500);
});

// ---------- 后台:工单 + 策略样本 / 纠偏数据分栏管理 ----------
function renderSampleCard(s, onChanged) {
  const c = document.createElement("div");
  c.className = "card";
  c.innerHTML = `
    <input class="s-q" value="${escapeHtml(s.question)}" />
    <textarea class="s-a">${escapeHtml(s.answer)}</textarea>
    <textarea class="s-n" placeholder="为什么这么说">${escapeHtml(s.note || "")}</textarea>
    <div class="meta">#${s.id} · ${sourceLabel(s.source)} · ${escapeHtml(s.created_at || "")}</div>
    <div class="actions">
      <button class="btn-ok">保存修改</button>
      <button class="btn-reject">删除</button>
    </div>`;
  const [save, remove] = c.querySelectorAll("button");
  save.onclick = async () => {
    save.disabled = true;
    const res = await put(`/api/playbook/${s.id}`, {
      question: c.querySelector(".s-q").value.trim(),
      answer: c.querySelector(".s-a").value.trim(),
      note: c.querySelector(".s-n").value.trim(),
    });
    save.disabled = false;
    if (res && res.ok) {
      save.textContent = "已保存 ✓";
      setTimeout(() => { save.textContent = "保存修改"; }, 1500);
    } else {
      alert("保存失败,请重试");
    }
  };
  remove.onclick = async () => {
    if (!confirm("确定删除这条样本?")) return;
    await del(`/api/playbook/${s.id}`);
    onChanged();
  };
  return c;
}

async function loadReview() {
  loadDirective();
  // 工单
  const tickets = await api("/api/tickets?status=open");
  const tbox = $("#tickets");
  tbox.innerHTML = tickets.length ? "" : '<div class="empty">没有待补的问题。问一个策略库接不住的问题，会在这里留下工单。</div>';
  tickets.forEach((t) => {
    const c = document.createElement("div");
    c.className = "card";
    c.innerHTML = `
      <div class="q">${escapeHtml(t.question)}</div>
      <div class="meta">工单 #${t.id} · ${t.created_at}</div>
      <textarea placeholder="标准答案 / 话术…"></textarea>
      <textarea placeholder="为什么这么说（可选）"></textarea>
      <div class="actions"><button class="btn-primary">补进策略库</button></div>`;
    const [ans, note] = c.querySelectorAll("textarea");
    c.querySelector("button").onclick = async () => {
      if (!ans.value.trim()) return alert("请先填写标准答案");
      await post(`/api/tickets/${t.id}/teach`, { answer: ans.value.trim(), note: note.value.trim() });
      loadReview(); refreshMetrics();
    };
    tbox.appendChild(c);
  });

  // 策略样本(主动沉淀 + 工单补充)
  const taught = await api("/api/playbook?source=" + encodeURIComponent(TRAIN_SOURCES));
  const taughtBox = $("#samples-taught");
  taughtBox.innerHTML = taught.length ? "" : '<div class="empty">还没有策略样本。</div>';
  taught.forEach((s) => taughtBox.appendChild(renderSampleCard(s, () => {
    loadReview(); refreshMetrics();
  })));

  // 纠偏数据(实测纠偏固化)
  const refined = await api("/api/playbook?source=" + encodeURIComponent(REFINE_SOURCES));
  const refineBox = $("#samples-refine");
  refineBox.innerHTML = refined.length ? "" : '<div class="empty">还没有纠偏记录。对话里纠正并写入之后会出现在这里。</div>';
  refined.forEach((s) => refineBox.appendChild(renderSampleCard(s, () => {
    loadReview(); refreshMetrics();
  })));
}

refreshMetrics();
