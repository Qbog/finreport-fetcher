const state = {
  bootstrap: null,
  report: null,
  sectionOrder: ["trend", "structure", "peer", "merge"],
  activeSectionIndex: 0,
  trendTemplateIndex: 0,
  trendCompanyIndex: 0,
  structureTemplateIndex: 0,
  structureCompanyIndex: 0,
  structureTimeIndex: 0,
  peerTemplateIndex: 0,
  peerTimeIndex: 0,
  mergeTemplateIndex: 0,
  mergeCompanyIndex: 0,
  categoryBuilderSelection: [],
};

const sectionLabelMap = {
  trend: "趋势分析",
  structure: "结构分析",
  peer: "同业分析",
  merge: "合并报表",
};

const statusText = document.getElementById("statusText");
const categorySelect = document.getElementById("categorySelect");
const templateGroups = document.getElementById("templateGroups");
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
const datasetHint = document.getElementById("datasetHint");
const categoryModal = document.getElementById("categoryModal");
const categoryNameInput = document.getElementById("categoryNameInput");
const companySearchInput = document.getElementById("companySearchInput");
const companyPickerList = document.getElementById("companyPickerList");
const selectedCompanyList = document.getElementById("selectedCompanyList");

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
  categorySelect.innerHTML = "";
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
  const groups = { trend: [], structure: [], peer: [], merge: [] };
  for (const tpl of templates) {
    if (groups[tpl.mode]) groups[tpl.mode].push(tpl);
  }
  templateGroups.innerHTML = "";
  for (const mode of state.sectionOrder) {
    const items = groups[mode] || [];
    if (!items.length) continue;
    const group = document.createElement("section");
    group.className = "template-group";
    group.innerHTML = `<h4>${sectionLabelMap[mode]}</h4>`;
    const wrap = document.createElement("div");
    wrap.className = "chip-wrap";
    for (const tpl of items) {
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
  if (!templates.length || !companies.length) return null;
  state.trendTemplateIndex = Math.min(Math.max(state.trendTemplateIndex, 0), templates.length - 1);
  state.trendCompanyIndex = Math.min(Math.max(state.trendCompanyIndex, 0), companies.length - 1);
  const tpl = templates[state.trendTemplateIndex];
  const comp = companies[state.trendCompanyIndex];
  const item = data.matrix?.[tpl.key]?.[comp.code6] || null;
  return { item, tpl, comp, templates, companies };
}

function getStructureItem() {
  const data = getSectionData("structure");
  const templates = data.templates || [];
  const companies = data.companies || [];
  const times = data.times || [];
  if (!templates.length || !companies.length || !times.length) return null;
  state.structureTemplateIndex = Math.min(Math.max(state.structureTemplateIndex, 0), templates.length - 1);
  state.structureCompanyIndex = Math.min(Math.max(state.structureCompanyIndex, 0), companies.length - 1);
  state.structureTimeIndex = Math.min(Math.max(state.structureTimeIndex, 0), times.length - 1);
  const tpl = templates[state.structureTemplateIndex];
  const comp = companies[state.structureCompanyIndex];
  const time = times[state.structureTimeIndex];
  const item = data.matrix?.[tpl.key]?.[comp.code6]?.[time] || null;
  return { item, tpl, comp, time, templates, companies, times };
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

function getMergeItem() {
  const data = getSectionData("merge");
  const templates = data.templates || [];
  const companies = data.companies || [];
  if (!templates.length || !companies.length) return null;
  state.mergeTemplateIndex = Math.min(Math.max(state.mergeTemplateIndex, 0), templates.length - 1);
  state.mergeCompanyIndex = Math.min(Math.max(state.mergeCompanyIndex, 0), companies.length - 1);
  const tpl = templates[state.mergeTemplateIndex];
  const comp = companies[state.mergeCompanyIndex];
  const item = data.matrix?.[tpl.key]?.[comp.code6] || null;
  return { item, tpl, comp, templates, companies };
}

function getCurrentView() {
  const mode = activeMode();
  if (mode === "trend") return getTrendItem();
  if (mode === "structure") return getStructureItem();
  if (mode === "peer") return getPeerItem();
  return getMergeItem();
}

function firstNonEmptySectionIndex() {
  for (let i = 0; i < state.sectionOrder.length; i += 1) {
    if ((getSectionData(state.sectionOrder[i]).templates || []).length) return i;
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
  wrapper.innerHTML = `<strong>${title}</strong>`;
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
    axisPanels.appendChild(buildAxisPanel("分析内容（← →）", view.templates, state.trendTemplateIndex, (idx) => {
      state.trendTemplateIndex = idx; renderViewer();
    }, item => item.label));
    axisPanels.appendChild(buildAxisPanel("公司（↑ ↓）", view.companies, state.trendCompanyIndex, (idx) => {
      state.trendCompanyIndex = idx; renderViewer();
    }, item => item.name));
    return;
  }
  if (mode === "structure") {
    axisPanels.appendChild(buildAxisPanel("结构内容", view.templates, state.structureTemplateIndex, (idx) => {
      state.structureTemplateIndex = idx; renderViewer();
    }, item => item.label));
    axisPanels.appendChild(buildAxisPanel("时间（← →）", view.times, state.structureTimeIndex, (idx) => {
      state.structureTimeIndex = idx; renderViewer();
    }, item => item));
    axisPanels.appendChild(buildAxisPanel("公司（↑ ↓）", view.companies, state.structureCompanyIndex, (idx) => {
      state.structureCompanyIndex = idx; renderViewer();
    }, item => item.name));
    return;
  }
  if (mode === "peer") {
    axisPanels.appendChild(buildAxisPanel("同业内容（↑ ↓）", view.templates, state.peerTemplateIndex, (idx) => {
      state.peerTemplateIndex = idx; renderViewer();
    }, item => item.label));
    axisPanels.appendChild(buildAxisPanel("时间（← →）", view.times, state.peerTimeIndex, (idx) => {
      state.peerTimeIndex = idx; renderViewer();
    }, item => item));
    return;
  }
  axisPanels.appendChild(buildAxisPanel("合并内容（← →）", view.templates, state.mergeTemplateIndex, (idx) => {
    state.mergeTemplateIndex = idx; renderViewer();
  }, item => item.label));
  axisPanels.appendChild(buildAxisPanel("公司（↑ ↓）", view.companies, state.mergeCompanyIndex, (idx) => {
    state.mergeCompanyIndex = idx; renderViewer();
  }, item => item.name));
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
      <strong>${escapeHtml(err.company || "全部公司")}${err.company ? " · " : ""}${escapeHtml(err.label || err.template || "模板")}${err.time ? " · " + escapeHtml(err.time) : ""}</strong>
      <pre>${escapeHtml(err.stderr || err.stdout || "执行失败")}</pre>
    </div>
  `).join("");
}

function renderViewer() {
  renderSectionTabs();
  renderErrors();
  if (!state.report) {
    viewerHeading.textContent = "图表浏览区";
    viewerSubheading.textContent = "按类别批量分析后，这里会展示图表和导航维度。";
    mainStage.innerHTML = '<div class="empty">先在左侧选择公司类别、时间范围和分析内容，然后点击“开始分析”。</div>';
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
  viewerHeading.textContent = `${sectionLabelMap[mode]} · ${state.report.category}`;
  viewerSubheading.textContent = `${state.report.start} → ${state.report.end}`;
  if (!view || !view.item) {
    mainStage.innerHTML = '<div class="empty">当前位置暂无图表，可以切换公司 / 时间 / 内容继续查看。</div>';
    captionTitle.textContent = "当前位置暂无图表";
    captionMeta.textContent = "你可以点击下方维度按钮，或使用方向键继续切换。";
    downloadXlsxLink.style.display = "none";
    openImageLink.style.display = "none";
    return;
  }
  mainStage.innerHTML = `<img src="${view.item.image}" alt="${escapeHtml(view.item.title)}">`;
  captionTitle.textContent = view.item.title || view.item.label || view.item.template || "图表";
  if (mode === "trend") {
    captionMeta.textContent = `公司：${view.comp.name} · 内容：${view.tpl.label}`;
  } else if (mode === "structure") {
    captionMeta.textContent = `公司：${view.comp.name} · 时间：${view.time} · 内容：${view.tpl.label}`;
  } else if (mode === "peer") {
    captionMeta.textContent = `时间：${view.time} · 内容：${view.tpl.label}`;
  } else {
    captionMeta.textContent = `公司：${view.comp.name} · 内容：${view.tpl.label}`;
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

function moveInCurrentSection(horizontalDelta, verticalDelta) {
  const mode = activeMode();
  if (mode === "trend") {
    const data = getSectionData("trend");
    const tplCount = (data.templates || []).length;
    const companyCount = (data.companies || []).length;
    if (tplCount && horizontalDelta) state.trendTemplateIndex = (state.trendTemplateIndex + horizontalDelta + tplCount) % tplCount;
    if (companyCount && verticalDelta) state.trendCompanyIndex = (state.trendCompanyIndex + verticalDelta + companyCount) % companyCount;
  } else if (mode === "structure") {
    const data = getSectionData("structure");
    const timeCount = (data.times || []).length;
    const companyCount = (data.companies || []).length;
    if (timeCount && horizontalDelta) state.structureTimeIndex = (state.structureTimeIndex + horizontalDelta + timeCount) % timeCount;
    if (companyCount && verticalDelta) state.structureCompanyIndex = (state.structureCompanyIndex + verticalDelta + companyCount) % companyCount;
  } else if (mode === "peer") {
    const data = getSectionData("peer");
    const timeCount = (data.times || []).length;
    const tplCount = (data.templates || []).length;
    if (timeCount && horizontalDelta) state.peerTimeIndex = (state.peerTimeIndex + horizontalDelta + timeCount) % timeCount;
    if (tplCount && verticalDelta) state.peerTemplateIndex = (state.peerTemplateIndex + verticalDelta + tplCount) % tplCount;
  } else {
    const data = getSectionData("merge");
    const tplCount = (data.templates || []).length;
    const companyCount = (data.companies || []).length;
    if (tplCount && horizontalDelta) state.mergeTemplateIndex = (state.mergeTemplateIndex + horizontalDelta + tplCount) % tplCount;
    if (companyCount && verticalDelta) state.mergeCompanyIndex = (state.mergeCompanyIndex + verticalDelta + companyCount) % companyCount;
  }
  renderViewer();
}

async function loadBootstrap() {
  setStatus("正在读取配置...");
  const data = await apiFetch("/api/bootstrap");
  state.bootstrap = data;
  renderCategories(data.categories || []);
  renderTemplateGroups(data.templates || []);
  datasetHint.textContent = `公司总表：${(data.companyBasics || []).length} 家；财报指标：${data.metricSummary?.rows || 0} 行 / ${data.metricSummary?.companies || 0} 家。`;
  setStatus("配置已加载，等待开始分析。");
}

function filteredBasics() {
  const basics = state.bootstrap?.companyBasics || [];
  const kw = (companySearchInput.value || "").trim();
  return basics.filter(item => !kw || item.name.includes(kw) || item.code6.includes(kw)).slice(0, 200);
}

function renderCategoryBuilder() {
  const selectedMap = new Map(state.categoryBuilderSelection.map(item => [item.code6, item]));
  const basics = filteredBasics();
  companyPickerList.innerHTML = basics.map(item => `
    <div class="picker-item">
      <div>
        <div>${escapeHtml(item.name)} <small>${escapeHtml(item.code6)}</small></div>
        <small>${escapeHtml(item.industry || "")}</small>
      </div>
      <button class="secondary picker-add-btn" data-code="${item.code6}" type="button">${selectedMap.has(item.code6) ? "已选" : "加入"}</button>
    </div>
  `).join("") || '<div class="empty">没有匹配的公司。</div>';

  selectedCompanyList.innerHTML = state.categoryBuilderSelection.map(item => `
    <div class="picker-item">
      <div>
        <div>${escapeHtml(item.name)} <small>${escapeHtml(item.code6)}</small></div>
        <small>${escapeHtml(item.industry || "")}</small>
      </div>
      <button class="ghost picker-remove-btn" data-code="${item.code6}" type="button">移除</button>
    </div>
  `).join("") || '<div class="empty">还没有选择公司。</div>';

  companyPickerList.querySelectorAll('.picker-add-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const code = btn.dataset.code;
      const found = (state.bootstrap?.companyBasics || []).find(x => x.code6 === code);
      if (!found) return;
      if (!state.categoryBuilderSelection.some(x => x.code6 === code)) {
        state.categoryBuilderSelection.push(found);
        renderCategoryBuilder();
      }
    });
  });

  selectedCompanyList.querySelectorAll('.picker-remove-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const code = btn.dataset.code;
      state.categoryBuilderSelection = state.categoryBuilderSelection.filter(x => x.code6 !== code);
      renderCategoryBuilder();
    });
  });
}

function openCategoryModal() {
  state.categoryBuilderSelection = [];
  categoryNameInput.value = "";
  companySearchInput.value = "";
  renderCategoryBuilder();
  categoryModal.style.display = "grid";
}

function closeCategoryModal() {
  categoryModal.style.display = "none";
}

async function createCategory() {
  const label = categoryNameInput.value.trim();
  const companies = state.categoryBuilderSelection.slice();
  if (!label) {
    alert("请先填写类别名称。");
    return;
  }
  if (!companies.length) {
    alert("请至少选择一家公司。");
    return;
  }
  setStatus("正在创建公司类别...");
  const data = await apiFetch("/api/categories/create", {
    method: "POST",
    body: JSON.stringify({ label, companies }),
  });
  renderCategories(data.categories || []);
  closeCategoryModal();
  setStatus(`已创建公司类别：${data.created}`);
}

async function createTemplate() {
  const mode = window.prompt("模板类别：trend / structure / peer / merge", "trend");
  if (!mode) return;
  const label = window.prompt("模板名称（显示名）");
  if (!label) return;
  let payload = { mode, label };
  if (mode === "merge") {
    const barItem = window.prompt("财务字段（如 is.revenue_total）", "is.revenue_total");
    const line = window.prompt("股价字段（默认 close）", "close");
    payload = { ...payload, barItem, line };
  } else {
    const expr = window.prompt("表达式（如 is.revenue_total / bs.total_assets / cf.net_cash_from_ops）", "is.revenue_total");
    if (!expr) return;
    payload = { ...payload, expr };
  }
  setStatus("正在创建模板...");
  const data = await apiFetch("/api/templates/create", { method: "POST", body: JSON.stringify(payload) });
  renderTemplateGroups(data.templates || []);
  setStatus(`已创建模板：${data.created}`);
}

async function generateReports() {
  const category = categorySelect.value;
  const start = document.getElementById("startInput").value;
  const end = document.getElementById("endInput").value;
  const templates = getSelectedTemplates();
  if (!category) return alert("请先选择公司类别。");
  if (!start || !end) return alert("请先设置时间范围。");
  if (!templates.length) return alert("请至少选择一个分析内容。");
  setStatus("正在按类别生成图表，请稍候...");
  document.getElementById("generateBtn").disabled = true;
  try {
    const data = await apiFetch("/api/generate", { method: "POST", body: JSON.stringify({ category, start, end, templates }) });
    state.report = data;
    state.activeSectionIndex = firstNonEmptySectionIndex();
    state.trendTemplateIndex = 0;
    state.trendCompanyIndex = 0;
    state.structureTemplateIndex = 0;
    state.structureCompanyIndex = 0;
    state.structureTimeIndex = 0;
    state.peerTemplateIndex = 0;
    state.peerTimeIndex = 0;
    state.mergeTemplateIndex = 0;
    state.mergeCompanyIndex = 0;
    setStatus(`分析完成：${data.category}，输出目录 ${data.reportDir}`);
    renderViewer();
  } catch (error) {
    console.error(error);
    setStatus(`分析失败：${error.message}`);
    alert(error.message);
  } finally {
    document.getElementById("generateBtn").disabled = false;
  }
}

function bindEvents() {
  document.getElementById("reloadBtn").addEventListener("click", loadBootstrap);
  document.getElementById("createCategoryBtn").addEventListener("click", openCategoryModal);
  document.getElementById("closeCategoryModalBtn").addEventListener("click", closeCategoryModal);
  document.getElementById("saveCategoryModalBtn").addEventListener("click", createCategory);
  companySearchInput.addEventListener("input", renderCategoryBuilder);
  categoryModal.addEventListener("click", (event) => {
    if (event.target === categoryModal) closeCategoryModal();
  });
  document.getElementById("createTemplateBtn").addEventListener("click", createTemplate);
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
    if (event.key === "ArrowLeft") { event.preventDefault(); moveInCurrentSection(-1, 0); }
    else if (event.key === "ArrowRight") { event.preventDefault(); moveInCurrentSection(1, 0); }
    else if (event.key === "ArrowUp") { event.preventDefault(); moveInCurrentSection(0, -1); }
    else if (event.key === "ArrowDown") { event.preventDefault(); moveInCurrentSection(0, 1); }
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
