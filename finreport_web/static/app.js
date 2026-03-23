const state = {
  bootstrap: null,
  report: null,
  sectionOrder: ["trend", "structure", "peer"],
  activeSectionIndex: 0,
  trendTemplateIndex: 0,
  trendCompanyIndex: 0,
  trendTimeIndex: 0,
  structureTemplateIndex: 0,
  structureTimeIndex: 0,
  peerTemplateIndex: 0,
  peerTimeIndex: 0,
};

const sectionLabelMap = {
  trend: "趋势分析",
  structure: "结构分析",
  peer: "同业分析",
};

const statusText = document.getElementById("statusText");
const categorySelect = document.getElementById("categorySelect");
const templateGroups = document.getElementById("templateGroups");
const configEditor = document.getElementById("configEditor");
const sectionTabs = document.getElementById("sectionTabs");
const mainStage = document.getElementById("mainStage");
const axisPanels = document.getElementById("axisPanels");
const viewerHeading = document.getElementById("viewerHeading");
const viewerSubheading = document.getElementById("viewerSubheading");
const captionTitle = document.getElementById("captionTitle");
const captionMeta = document.getElementById("captionMeta");
const downloadXlsxLink = document.getElementById("downloadXlsxLink");
const openImageLink = document.getElementById("openImageLink");
const errorBox = document.getElementById("errorBox");

function setStatus(text) {
  statusText.textContent = text;
}

function setDefaultDates() {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  document.getElementById("endInput").value = `${yyyy}-${mm}-${dd}`;
  document.getElementById("startInput").value = `${yyyy - 2}-01-01`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function apiFetch(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || `请求失败: ${response.status}`);
  }
  return data;
}

function renderCategories(categories) {
  const current = categorySelect.value;
  categorySelect.innerHTML = '<option value="">不指定</option>';
  for (const cat of categories) {
    const option = document.createElement("option");
    option.value = cat.key;
    option.textContent = `${cat.label}（${cat.items.length}）`;
    categorySelect.appendChild(option);
  }
  if ([...categorySelect.options].some(opt => opt.value === current)) {
    categorySelect.value = current;
  }
}

function renderTemplateGroups(templates) {
  const groups = { trend: [], structure: [], peer: [] };
  for (const tpl of templates) {
    if (groups[tpl.mode]) groups[tpl.mode].push(tpl);
  }

  templateGroups.innerHTML = "";
  for (const mode of state.sectionOrder) {
    const group = document.createElement("section");
    group.className = "template-group";
    const title = document.createElement("h4");
    title.textContent = sectionLabelMap[mode];
    group.appendChild(title);

    const wrap = document.createElement("div");
    wrap.className = "chip-wrap";

    for (const tpl of groups[mode]) {
      const label = document.createElement("label");
      label.className = "chip";
      label.innerHTML = `<input type="checkbox" class="tpl-check" value="${escapeHtml(tpl.key)}" checked> <span>${escapeHtml(tpl.label)}</span>`;
      wrap.appendChild(label);
    }

    group.appendChild(wrap);
    templateGroups.appendChild(group);
  }
}

function getSelectedTemplates() {
  return [...document.querySelectorAll(".tpl-check:checked")].map(el => el.value);
}

function activeMode() {
  return state.sectionOrder[state.activeSectionIndex] || "trend";
}

function getSectionData(mode) {
  return state.report?.sections?.[mode] || {};
}

function getTrendItem() {
  const data = getSectionData("trend");
  const templates = data.templates || [];
  const companies = data.companies || [];
  const times = data.times || [];
  if (!templates.length || !companies.length || !times.length) return null;

  state.trendTemplateIndex = Math.min(Math.max(state.trendTemplateIndex, 0), templates.length - 1);
  state.trendCompanyIndex = Math.min(Math.max(state.trendCompanyIndex, 0), companies.length - 1);
  state.trendTimeIndex = Math.min(Math.max(state.trendTimeIndex, 0), times.length - 1);

  const tpl = templates[state.trendTemplateIndex];
  const comp = companies[state.trendCompanyIndex];
  const time = times[state.trendTimeIndex];
  const item = data.matrix?.[tpl.key]?.[comp.code6]?.[time] || null;
  return { item, tpl, comp, time, templates, companies, times };
}

function getStructureItem() {
  const data = getSectionData("structure");
  const templates = data.templates || [];
  const times = data.times || [];
  if (!templates.length || !times.length) return null;

  state.structureTemplateIndex = Math.min(Math.max(state.structureTemplateIndex, 0), templates.length - 1);
  state.structureTimeIndex = Math.min(Math.max(state.structureTimeIndex, 0), times.length - 1);

  const tpl = templates[state.structureTemplateIndex];
  const time = times[state.structureTimeIndex];
  const item = data.matrix?.[tpl.key]?.[time] || null;
  return { item, tpl, time, templates, times };
}

function getPeerItem() {
  const data = getSectionData("peer");
  const templates = data.templates || [];
  const times = data.times || [];
  if (!templates.length || !times.length) return null;

  state.peerTemplateIndex = Math.min(Math.max(state.peerTemplateIndex, 0), templates.length - 1);
  state.peerTimeIndex = Math.min(Math.max(state.peerTimeIndex, 0), times.length - 1);

  const tpl = templates[state.peerTemplateIndex];
  const time = times[state.peerTimeIndex];
  const item = data.matrix?.[tpl.key]?.[time] || null;
  return { item, tpl, time, templates, times };
}

function getCurrentView() {
  const mode = activeMode();
  if (mode === "trend") return getTrendItem();
  if (mode === "structure") return getStructureItem();
  return getPeerItem();
}

function firstNonEmptySectionIndex() {
  for (let i = 0; i < state.sectionOrder.length; i += 1) {
    const mode = state.sectionOrder[i];
    const data = getSectionData(mode);
    if ((data.templates || []).length) return i;
  }
  return 0;
}

function renderSectionTabs() {
  sectionTabs.innerHTML = "";
  for (let i = 0; i < state.sectionOrder.length; i += 1) {
    const mode = state.sectionOrder[i];
    const count = (getSectionData(mode).templates || []).length;
    const button = document.createElement("button");
    button.type = "button";
    button.className = `section-tab ${i === state.activeSectionIndex ? "active" : ""}`;
    button.textContent = `${sectionLabelMap[mode]} · ${count}`;
    button.disabled = count === 0;
    button.addEventListener("click", () => {
      state.activeSectionIndex = i;
      renderViewer();
    });
    sectionTabs.appendChild(button);
  }
}

function buildAxisPanel(title, items, activeIndex, onSelect, formatter) {
  const wrapper = document.createElement("div");
  wrapper.className = "axis-panel";
  const strong = document.createElement("strong");
  strong.textContent = title;
  wrapper.appendChild(strong);

  const chips = document.createElement("div");
  chips.className = "axis-chip-wrap";
  items.forEach((item, idx) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `axis-chip ${idx === activeIndex ? "active" : ""}`;
    btn.textContent = formatter(item);
    btn.addEventListener("click", () => onSelect(idx));
    chips.appendChild(btn);
  });
  wrapper.appendChild(chips);
  return wrapper;
}

function renderAxisPanels(view) {
  axisPanels.innerHTML = "";
  if (!view) return;

  const mode = activeMode();
  if (mode === "trend") {
    axisPanels.appendChild(buildAxisPanel("趋势科目（点击切换）", view.templates, state.trendTemplateIndex, (idx) => {
      state.trendTemplateIndex = idx;
      renderViewer();
    }, (item) => item.label));
    axisPanels.appendChild(buildAxisPanel("公司（↑ ↓）", view.companies, state.trendCompanyIndex, (idx) => {
      state.trendCompanyIndex = idx;
      renderViewer();
    }, (item) => item.name));
    axisPanels.appendChild(buildAxisPanel("时间（← →）", view.times, state.trendTimeIndex, (idx) => {
      state.trendTimeIndex = idx;
      renderViewer();
    }, (item) => item));
    return;
  }

  if (mode === "structure") {
    axisPanels.appendChild(buildAxisPanel("分析科目（↑ ↓）", view.templates, state.structureTemplateIndex, (idx) => {
      state.structureTemplateIndex = idx;
      renderViewer();
    }, (item) => item.label));
    axisPanels.appendChild(buildAxisPanel("时间（← →）", view.times, state.structureTimeIndex, (idx) => {
      state.structureTimeIndex = idx;
      renderViewer();
    }, (item) => item));
    return;
  }

  axisPanels.appendChild(buildAxisPanel("同业科目（← →）", view.templates, state.peerTemplateIndex, (idx) => {
    state.peerTemplateIndex = idx;
    renderViewer();
  }, (item) => item.label));
  axisPanels.appendChild(buildAxisPanel("时间（↑ ↓）", view.times, state.peerTimeIndex, (idx) => {
    state.peerTimeIndex = idx;
    renderViewer();
  }, (item) => item));
}

function renderErrors() {
  const errors = state.report?.errors || [];
  if (!errors.length) {
    errorBox.style.display = "none";
    errorBox.innerHTML = "";
    return;
  }

  errorBox.style.display = "block";
  errorBox.innerHTML = `<div class="section-title"><h3>生成提示 / 错误</h3></div>` + errors.map(err => `
    <div class="error-card">
      <strong>${escapeHtml(err.company || "")}${err.company ? " · " : ""}${escapeHtml(err.label || err.template || "模板")}${err.time ? " · " + escapeHtml(err.time) : ""}</strong>
      <pre>${escapeHtml(err.stderr || err.stdout || "执行失败")}</pre>
    </div>
  `).join("");
}

function renderViewer() {
  renderSectionTabs();
  renderErrors();

  if (!state.report) {
    viewerHeading.textContent = "图表浏览区";
    viewerSubheading.textContent = "生成后会按趋势分析 / 结构分析 / 同业分析分类展示。";
    mainStage.innerHTML = '<div class="empty">先在左侧设置公司和时间范围，然后点击“生成全部图表”。</div>';
    axisPanels.innerHTML = "";
    captionTitle.textContent = "暂无图表";
    captionMeta.textContent = "生成后可在此查看图片与下载 Excel。";
    downloadXlsxLink.style.display = "none";
    openImageLink.style.display = "none";
    return;
  }

  if (!(getSectionData(activeMode()).templates || []).length) {
    state.activeSectionIndex = firstNonEmptySectionIndex();
  }

  const mode = activeMode();
  const view = getCurrentView();
  renderAxisPanels(view);

  viewerHeading.textContent = `${state.report.company.name} · ${sectionLabelMap[mode]}`;
  viewerSubheading.textContent = `${state.report.start} → ${state.report.end}` + (state.report.category ? ` · 分类：${state.report.category}` : "");

  if (!view || !view.item) {
    mainStage.innerHTML = '<div class="empty">当前位置暂无图表，可以换一个时间、公司或科目继续看。</div>';
    captionTitle.textContent = "当前位置暂无图表";
    captionMeta.textContent = "你可以点击下方维度按钮，或使用方向键继续切换。";
    downloadXlsxLink.style.display = "none";
    openImageLink.style.display = "none";
    return;
  }

  mainStage.innerHTML = `<img src="${view.item.image}" alt="${escapeHtml(view.item.title)}">`;
  captionTitle.textContent = view.item.title || view.item.label || view.item.template || "图表";

  if (mode === "trend") {
    captionMeta.textContent = `公司：${view.comp.name} · 截止：${view.time} · 模板：${view.tpl.label}`;
  } else if (mode === "structure") {
    captionMeta.textContent = `科目：${view.tpl.label} · 期末：${view.time}`;
  } else {
    captionMeta.textContent = `科目：${view.tpl.label} · 期末：${view.time}`;
  }

  openImageLink.href = view.item.image;
  openImageLink.style.display = "inline-flex";
  if (view.item.xlsx) {
    downloadXlsxLink.href = view.item.xlsx;
    downloadXlsxLink.style.display = "inline-flex";
  } else {
    downloadXlsxLink.style.display = "none";
  }
}

function moveSection(delta) {
  if (!state.report) return;
  let idx = state.activeSectionIndex;
  for (let step = 0; step < state.sectionOrder.length; step += 1) {
    idx = (idx + delta + state.sectionOrder.length) % state.sectionOrder.length;
    if ((getSectionData(state.sectionOrder[idx]).templates || []).length) {
      state.activeSectionIndex = idx;
      renderViewer();
      return;
    }
  }
}

function moveInCurrentSection(horizontalDelta, verticalDelta) {
  const mode = activeMode();
  if (mode === "trend") {
    const data = getSectionData("trend");
    const timeCount = (data.times || []).length;
    const companyCount = (data.companies || []).length;
    if (timeCount && horizontalDelta) state.trendTimeIndex = (state.trendTimeIndex + horizontalDelta + timeCount) % timeCount;
    if (companyCount && verticalDelta) state.trendCompanyIndex = (state.trendCompanyIndex + verticalDelta + companyCount) % companyCount;
  } else if (mode === "structure") {
    const data = getSectionData("structure");
    const timeCount = (data.times || []).length;
    const tplCount = (data.templates || []).length;
    if (timeCount && horizontalDelta) state.structureTimeIndex = (state.structureTimeIndex + horizontalDelta + timeCount) % timeCount;
    if (tplCount && verticalDelta) state.structureTemplateIndex = (state.structureTemplateIndex + verticalDelta + tplCount) % tplCount;
  } else {
    const data = getSectionData("peer");
    const timeCount = (data.times || []).length;
    const tplCount = (data.templates || []).length;
    if (tplCount && horizontalDelta) state.peerTemplateIndex = (state.peerTemplateIndex + horizontalDelta + tplCount) % tplCount;
    if (timeCount && verticalDelta) state.peerTimeIndex = (state.peerTimeIndex + verticalDelta + timeCount) % timeCount;
  }
  renderViewer();
}

async function loadBootstrap() {
  setStatus("正在读取配置...");
  const data = await apiFetch("/api/bootstrap");
  state.bootstrap = data;
  renderCategories(data.categories || []);
  renderTemplateGroups(data.templates || []);
  configEditor.value = data.configText || "";
  setStatus("配置已加载，等待生成图表。");
}

async function saveCategories() {
  const text = configEditor.value;
  setStatus("正在保存分类配置...");
  const data = await apiFetch("/api/categories/save", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
  renderCategories(data.categories || []);
  setStatus("分类配置已保存。");
}

async function generateReports() {
  const company = document.getElementById("companyInput").value.trim();
  const start = document.getElementById("startInput").value;
  const end = document.getElementById("endInput").value;
  const category = categorySelect.value;
  const templates = getSelectedTemplates();

  if (!company) {
    alert("请先输入公司代码或名称。");
    return;
  }
  if (!start || !end) {
    alert("请先设置时间范围。");
    return;
  }
  if (!templates.length) {
    alert("请至少选择一个模板。");
    return;
  }

  setStatus("正在生成图表，请稍候...");
  document.getElementById("generateBtn").disabled = true;

  try {
    const data = await apiFetch("/api/generate", {
      method: "POST",
      body: JSON.stringify({ company, start, end, category, templates }),
    });
    state.report = data;
    state.activeSectionIndex = firstNonEmptySectionIndex();
    state.trendTemplateIndex = 0;
    state.trendCompanyIndex = 0;
    state.trendTimeIndex = 0;
    state.structureTemplateIndex = 0;
    state.structureTimeIndex = 0;
    state.peerTemplateIndex = 0;
    state.peerTimeIndex = 0;
    setStatus(`生成完成：${data.company.name}，输出目录 ${data.reportDir}`);
    renderViewer();
  } catch (error) {
    console.error(error);
    setStatus(`生成失败：${error.message}`);
    alert(error.message);
  } finally {
    document.getElementById("generateBtn").disabled = false;
  }
}

function bindEvents() {
  document.getElementById("reloadBtn").addEventListener("click", loadBootstrap);
  document.getElementById("saveConfigBtn").addEventListener("click", saveCategories);
  document.getElementById("generateBtn").addEventListener("click", generateReports);
  document.getElementById("selectAllTplBtn").addEventListener("click", () => {
    document.querySelectorAll(".tpl-check").forEach(el => { el.checked = true; });
  });
  document.getElementById("clearTplBtn").addEventListener("click", () => {
    document.querySelectorAll(".tpl-check").forEach(el => { el.checked = false; });
  });

  document.addEventListener("keydown", (event) => {
    const tag = document.activeElement?.tagName || "";
    if (["INPUT", "TEXTAREA", "SELECT"].includes(tag)) return;
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      moveInCurrentSection(-1, 0);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      moveInCurrentSection(1, 0);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      moveInCurrentSection(0, -1);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      moveInCurrentSection(0, 1);
    } else if (event.key === "PageUp") {
      event.preventDefault();
      moveSection(-1);
    } else if (event.key === "PageDown") {
      event.preventDefault();
      moveSection(1);
    }
  });
}

window.addEventListener("DOMContentLoaded", async () => {
  setDefaultDates();
  bindEvents();
  renderViewer();
  try {
    await loadBootstrap();
  } catch (error) {
    console.error(error);
    setStatus(`加载失败：${error.message}`);
  }
});
