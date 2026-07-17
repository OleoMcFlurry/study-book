const el = (id) => document.getElementById(id);
const LEVELS = [
  ["unknown", "不了解"],
  ["heard", "了解"],
  ["understood", "掌握"],
  ["proficient", "熟练掌握"],
  ["expert", "精通"],
];

const LLM_STORAGE_KEY = "knowledge_path_demo_llm_v1";

let sessionId = null;

function showError(err) {
  const box = el("error");
  box.hidden = false;
  box.textContent =
    typeof err === "string" ? err : JSON.stringify(err, null, 2);
}

function clearError() {
  el("error").hidden = true;
  el("error").textContent = "";
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail || data;
    throw detail;
  }
  return data;
}

function loadLlmForm() {
  try {
    const raw = localStorage.getItem(LLM_STORAGE_KEY);
    if (!raw) return;
    const cfg = JSON.parse(raw);
    if (cfg.api_key) el("api-key").value = cfg.api_key;
    if (cfg.base_url) el("base-url").value = cfg.base_url;
    if (cfg.model) el("model").value = cfg.model;
    if (cfg.reasoning_effort)
      el("reasoning-effort").value = cfg.reasoning_effort;
    if (cfg.max_tokens != null) el("max-tokens").value = cfg.max_tokens;
    if (cfg.temperature != null) el("temperature").value = cfg.temperature;
    el("enable-thinking").checked = !!cfg.enable_thinking;
  } catch (_) {
    /* 忽略损坏的本地配置 */
  }
}

function saveLlmForm() {
  const cfg = collectLlmOverride(true);
  localStorage.setItem(LLM_STORAGE_KEY, JSON.stringify(cfg));
}

/** @param {boolean} forStorage 是否把空字段也写入存储 */
function collectLlmOverride(forStorage = false) {
  const api_key = el("api-key").value.trim();
  const base_url = el("base-url").value.trim();
  const model = el("model").value.trim();
  const reasoning_effort = el("reasoning-effort").value;
  const maxRaw = el("max-tokens").value.trim();
  const tempRaw = el("temperature").value.trim();
  const enable_thinking = el("enable-thinking").checked;

  const out = {};
  if (forStorage || api_key) out.api_key = api_key;
  if (forStorage || base_url) out.base_url = base_url;
  if (forStorage || model) out.model = model;
  if (forStorage || reasoning_effort !== "none")
    out.reasoning_effort = reasoning_effort;
  if (maxRaw) {
    const n = Number(maxRaw);
    if (Number.isFinite(n) && n > 0) out.max_tokens = Math.floor(n);
  } else if (forStorage) {
    out.max_tokens = null;
  }
  if (tempRaw !== "") {
    const t = Number(tempRaw);
    if (Number.isFinite(t)) out.temperature = t;
  }
  if (forStorage || enable_thinking) out.enable_thinking = enable_thinking;
  return out;
}
function llmBody() {
  // 始终提交 llm 对象，避免服务端只读环境变量而忽略界面密钥
  const llm = collectLlmOverride(false);
  return { llm };
}

function renderSession(s) {
  sessionId = s.session_id;
  el("session-id").textContent = s.session_id;
  el("status").textContent = s.status;
  el("btn-graph").disabled = false;
  el("btn-path").disabled = !s.graph;
  renderTree(s);
  renderPath(s.path || []);
}

function renderTree(s) {
  const root = el("tree");
  root.innerHTML = "";
  if (!s.graph || !s.graph.nodes) {
    root.textContent = "尚未生成依赖图。";
    return;
  }
  const mastery = s.mastery || {};
  const gaps = new Set(s.gaps || []);
  for (const n of s.graph.nodes) {
    const div = document.createElement("div");
    div.className = "node";
    const mark = gaps.has(n.id) ? "【缺口】" : "";
    div.innerHTML = `<h3>${mark}${n.title} <small>(${n.id})</small></h3><p>${
      n.description || ""
    }</p>`;
    const sel = document.createElement("select");
    for (const [v, label] of LEVELS) {
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = label;
      if ((mastery[n.id] || "unknown") === v) opt.selected = true;
      sel.appendChild(opt);
    }
    sel.addEventListener("change", async () => {
      clearError();
      try {
        const updated = await api(`/api/sessions/${sessionId}/mastery`, {
          method: "PUT",
          body: JSON.stringify({ node_id: n.id, level: sel.value }),
        });
        renderSession(updated);
      } catch (e) {
        showError(e);
      }
    });
    div.appendChild(sel);
    root.appendChild(div);
  }
  if (s.graph.edges && s.graph.edges.length) {
    const edges = document.createElement("p");
    edges.textContent =
      "依赖：" + s.graph.edges.map((e) => `${e.from} → ${e.to}`).join("； ");
    root.appendChild(edges);
  }
}

function renderPath(path) {
  const ol = el("path");
  ol.innerHTML = "";
  if (!path.length) {
    ol.textContent = "";
    return;
  }
  for (const item of path) {
    const li = document.createElement("li");
    const actions = (item.actions || []).map((a) => `<li>${a}</li>`).join("");
    li.innerHTML = `<strong>${
      item.title
    }</strong><ul>${actions}</ul><em>验收：${
      item.acceptance_question || ""
    }</em>`;
    ol.appendChild(li);
  }
}

el("btn-save-llm").addEventListener("click", () => {
  clearError();
  saveLlmForm();
  el("llm-server-hint").textContent = "模型配置已保存到本机浏览器。";
});

el("btn-create").addEventListener("click", async () => {
  clearError();
  const goal = el("goal").value.trim();
  const background = el("background").value.trim();
  const keywords = el("keywords")
    .value.split(/[,，]/)
    .map((s) => s.trim())
    .filter(Boolean);
  try {
    const s = await api("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ goal, background, known_keywords: keywords }),
    });
    renderSession(s);
  } catch (e) {
    showError(e);
  }
});

el("btn-graph").addEventListener("click", async () => {
  clearError();
  if (!sessionId) return;
  try {
    const s = await api(`/api/sessions/${sessionId}/graph`, {
      method: "POST",
      body: JSON.stringify(llmBody()),
    });
    renderSession(s);
  } catch (e) {
    showError(e);
  }
});

el("btn-path").addEventListener("click", async () => {
  clearError();
  if (!sessionId) return;
  try {
    const s = await api(`/api/sessions/${sessionId}/path`, {
      method: "POST",
      body: JSON.stringify(llmBody()),
    });
    renderSession(s);
  } catch (e) {
    showError(e);
  }
});

async function bootstrap() {
  loadLlmForm();
  try {
    const d = await api("/api/llm/defaults");
    if (!el("base-url").value && d.base_url) el("base-url").value = d.base_url;
    if (!el("model").value && d.model) el("model").value = d.model;
    if (!el("reasoning-effort").value && d.reasoning_effort) {
      el("reasoning-effort").value = d.reasoning_effort;
    }
    if (!el("max-tokens").value && d.max_tokens)
      el("max-tokens").value = d.max_tokens;
    if (d.enable_thinking) el("enable-thinking").checked = true;
    el("llm-server-hint").textContent = d.has_server_api_key
      ? "服务端已配置默认 API Key；界面留空将使用服务端密钥。"
      : "服务端未配置默认 API Key；生成图/路径前请在界面填写密钥。";
  } catch (e) {
    el("llm-server-hint").textContent = "无法读取服务端默认配置。";
  }
}

bootstrap();
