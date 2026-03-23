const state = {
  bootstrap: null,
  report: null,
  sectionOrder: ["trend", "structure", "peer"],
  activeSectionIndex: 0,
  activeItemIndex: { trend: 0, structure: 0, peer: 0 },
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
const thumbList = document.getElementById("thumbList");
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

function getSectionBundles(mode) {
  return state.report?.sections?.[mode] || [];
}

function getSectionItems(mode) {
  return getSectionBundles(mode).flatMap(bundle => bundle.items || []);
}

function getFirstNonEmptySectionIndex() {
  for (let i = 0; i < state.sectionOrder.length; i += 1) {
    if (getSectionItems(state.sectionOrder[i]).length > 0) return i;
  }
  return 0;
}

function clampActiveIndex(mode) {
  const items = getSectionItems(mode);
  if (!items.length) {
    state.activeItemIndex[mode] = 0;
    return;
  }
  if (state.activeItemIndex[mode] >= items.length) state.activeItemIndex[mode] = items.length - 1;
  if (state.activeItemIndex[mode] < 0) state.activeItemIndex[mode] = 0;
}

function activeMode() {
  return state.sectionOrder[state.activeSectionIndex] || "trend";
}

function activeItem() {
  const mode = activeMode();
  clampActiveIndex(mode);
  const items = getSectionItems(mode);
  return items[state.activeItemIndex[mode]] || null;
}

function renderSectionTabs() {
  sectionTabs.innerHTML = "";
  for (let i = 0; i < state.sectionOrder.length; i += 1) {
    const mode = state.sectionOrder[i];
    const items = getSectionItems(mode);
    const button = document.createElement("button");
    button.type = "button";
    button.className = `section-tab ${i === state.activeSectionIndex ? "active" : ""}`;
    button.textContent = `${sectionLabelMap[mode]} · ${items.length}`;
    button.disabled = items.length === 0;
    button.addEventListener("click", () => {
      state.activeSectionIndex = i;
      renderViewer();
    });
    sectionTabs.appendChild(button);
  }
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
      <strong>${escapeHtml(err.label || err.template || "模板")}</strong>
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
    thumbList.innerHTML = "";
    captionTitle.textContent = "暂无图表";
    captionMeta.textContent = "生成后可在此查看图片与下载 Excel。";
    downloadXlsxLink.style.display = "none";
    openImageLink.style.display = "none";
    return;
  }

  const mode = activeMode();
  const items = getSectionItems(mode);
  if (!items.length) {
    state.activeSectionIndex = getFirstNonEmptySectionIndex();
  }
  const currentMode = activeMode();
  const currentItems = getSectionItems(currentMode);
  clampActiveIndex(currentMode);
  const currentItem = activeItem();

  viewerHeading.textContent = `${state.report.company.name} · ${sectionLabelMap[currentMode]}`;
  viewerSubheading.textContent = `${state.report.start} → ${state.report.end}` + (state.report.category ? ` · 分类：${state.report.category}` : "");

  if (!currentItem) {
    mainStage.innerHTML = '<div class="empty">这个分析分类暂时没有生成出图表。</div>';
    thumbList.innerHTML = "";
    captionTitle.textContent = "暂无图表";
    captionMeta.textContent = "请选择其它分析分类，或检查模板配置。";
    downloadXlsxLink.style.display = "none";
    openImageLink.style.display = "none";
    return;
  }

  mainStage.innerHTML = `<img src="${currentItem.image}" alt="${escapeHtml(currentItem.title)}">`;
  captionTitle.textContent = currentItem.title || currentItem.label || currentItem.template || "图表";
  captionMeta.textContent = `${sectionLabelMap[currentMode]} · ${state.activeItemIndex[currentMode] + 1} / ${currentItems.length} · ${currentItem.filename}`;

  openImageLink.href = currentItem.image;
  openImageLink.style.display = "inline-flex";
  if (currentItem.xlsx) {
    downloadXlsxLink.href = currentItem.xlsx;
    downloadXlsxLink.style.display = "inline-flex";
  } else {
    downloadXlsxLink.style.display = "none";
  }

  thumbList.innerHTML = currentItems.map((item, idx) => `
    <div class="thumb ${idx === state.activeItemIndex[currentMode] ? "active" : ""}" data-index="${idx}">
      <img src="${item.image}" alt="${escapeHtml(item.title)}">
      <strong>${escapeHtml(item.title)}</strong>
      <span>${escapeHtml(item.filename)}</span>
    </div>
  `).join("");

  thumbList.querySelectorAll(".thumb").forEach(el => {
    el.addEventListener("click", () => {
      state.activeItemIndex[currentMode] = Number(el.dataset.index || 0);
      renderViewer();
    });
  });
}

function moveSection(delta) {
  if (!state.report) return;
  let idx = state.activeSectionIndex;
  for (let step = 0; step < state.sectionOrder.length; step += 1) {
    idx = (idx + delta + state.sectionOrder.length) % state.sectionOrder.length;
    if (getSectionItems(state.sectionOrder[idx]).length > 0) {
      state.activeSectionIndex = idx;
      renderViewer();
      return;
    }
  }
}

function moveItem(delta) {
  if (!state.report) return;
  const mode = activeMode();
  const items = getSectionItems(mode);
  if (!items.length) return;
  state.activeItemIndex[mode] = (state.activeItemIndex[mode] + delta + items.length) % items.length;
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
    state.activeSectionIndex = getFirstNonEmptySectionIndex();
    state.activeItemIndex = { trend: 0, structure: 0, peer: 0 };
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
      moveItem(-1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      moveItem(1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      moveSection(-1);
    } else if (event.key === "ArrowDown") {
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
