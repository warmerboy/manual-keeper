/* 说明书保管箱前端：单页应用，原生 JS */

const $ = (id) => document.getElementById(id);
const state = {
  filter: { type: null, value: null }, // type: category/subcategory/vendor/model/review/search/all
  currentId: null,
  cards: [],
};

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = `请求失败 ${res.status}`;
    try { const j = await res.json(); msg += `: ${j.detail || JSON.stringify(j)}`; } catch {}
    throw new Error(msg);
  }
  return res.json();
}

function toast(msg, dur = 3500) {
  const el = $("upload-toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (el.hidden = true), dur);
}

/* ---- 上传进度卡片栈（多份并行可叠加） ---- */
function newProgressCard(initialMsg) {
  const stack = $("upload-progress");
  const card = document.createElement("div");
  card.className = "progress-card running";
  card.innerHTML = `
    <span class="mini-spinner"></span>
    <span class="content"></span>
  `;
  card.querySelector(".content").textContent = initialMsg;

  let dismissTimer = null;
  let pendingMs = 0;
  card._scheduleDismiss = (ms) => {
    pendingMs = ms;
    if (dismissTimer) clearTimeout(dismissTimer);
    dismissTimer = setTimeout(() => fadeAndRemove(card), ms);
  };
  card.addEventListener("mouseenter", () => {
    if (dismissTimer) { clearTimeout(dismissTimer); dismissTimer = null; }
  });
  card.addEventListener("mouseleave", () => {
    if (!dismissTimer && pendingMs > 0) dismissTimer = setTimeout(() => fadeAndRemove(card), 2500);
  });

  stack.appendChild(card);
  return card;
}

function updateProgressCard(card, status, msg) {
  card.className = `progress-card ${status}`;
  const iconMap = { running: '<span class="mini-spinner"></span>', done: '<span class="icon">✓</span>', error: '<span class="icon">⚠</span>' };
  card.innerHTML = `
    ${iconMap[status] || ''}
    <span class="content"></span>
    ${status !== 'running' ? '<button class="close" title="关闭">×</button>' : ''}
  `;
  card.querySelector(".content").textContent = msg;
  const closeBtn = card.querySelector(".close");
  if (closeBtn) closeBtn.onclick = () => fadeAndRemove(card);
}

function fadeAndRemove(card) {
  if (card.classList.contains("fading")) return;
  card.classList.add("fading");
  setTimeout(() => card.remove(), 300);
}

/* ---- 分类树 ---- */
async function loadTree() {
  try {
    const { tree } = await api("/api/tree");
    renderTree(tree);
    await refreshReviewBadge();
  } catch (e) { toast(e.message); }
}

function renderTree(tree) {
  const root = $("tree");
  root.innerHTML = "";
  const allNode = nodeEl("全部文档", null, true);
  allNode.dataset.filterType = "all";
  allNode.onclick = () => setFilter({ type: "all" });
  root.appendChild(allNode);

  // v2: 2 层（大类 → 细类）。count 为 0 的大类也展示，标灰
  tree.forEach((cat) => {
    const catEl = nodeEl(cat.name, cat.count);
    catEl.dataset.filterType = "category";
    catEl.dataset.filterValue = cat.name;
    if (!cat.count) catEl.style.opacity = "0.45";
    catEl.onclick = (ev) => { ev.stopPropagation(); setFilter({ type: "category", value: cat.name }); };
    root.appendChild(catEl);

    if (cat.children?.length) {
      const subWrap = document.createElement("div");
      subWrap.className = "tree-children";
      cat.children.forEach((sub) => {
        const subEl = nodeEl(sub.name, sub.count);
        subEl.dataset.filterType = "subcategory";
        subEl.dataset.filterValue = sub.name;
        subEl.dataset.category = cat.name;
        subEl.onclick = (ev) => { ev.stopPropagation(); setFilter({ type: "subcategory", value: sub.name, parent: cat.name }); };
        subWrap.appendChild(subEl);
      });
      root.appendChild(subWrap);
    }
  });
}

function nodeEl(name, count, isAll = false) {
  const el = document.createElement("div");
  el.className = "tree-node";
  const left = document.createElement("span");
  left.textContent = isAll ? "📚 " + name : name;
  el.appendChild(left);
  if (count !== null && count !== undefined) {
    const c = document.createElement("span");
    c.className = "tree-count";
    c.textContent = count;
    el.appendChild(c);
  }
  return el;
}

function highlightTreeNode() {
  document.querySelectorAll(".tree-node").forEach((n) => n.classList.remove("active"));
  const { type, value } = state.filter;
  if (type === "all") {
    document.querySelector('[data-filter-type="all"]')?.classList.add("active");
    return;
  }
  document.querySelectorAll(".tree-node").forEach((n) => {
    if (n.dataset.filterType === type && n.dataset.filterValue === value) n.classList.add("active");
  });
}

/* ---- 列表 ---- */
async function setFilter(filter) {
  state.filter = filter;
  highlightTreeNode();
  $("search-input").value = "";
  await loadList();
}

async function loadList() {
  let url = "/api/documents?limit=300";
  let title = "全部文档";
  const f = state.filter;
  if (f.type === "category") { url += `&category=${encodeURIComponent(f.value)}`; title = f.value; }
  else if (f.type === "subcategory") { url += `&subcategory=${encodeURIComponent(f.value)}`; title = f.value; }
  else if (f.type === "vendor") { url += `&vendor=${encodeURIComponent(f.value)}`; title = f.value; }
  else if (f.type === "review") { url += `&needs_review=true`; title = "待确认"; }
  else if (f.type === "search") {
    const { items, count } = await api(`/api/search?q=${encodeURIComponent(f.value)}`);
    renderCards(items);
    $("list-title").textContent = `搜索：${f.value}`;
    $("list-count").textContent = `${count} 条`;
    return;
  }

  try {
    const { items, count } = await api(url);
    $("list-title").textContent = title;
    $("list-count").textContent = `${count} 条`;
    renderCards(items);
  } catch (e) { toast(e.message); }
}

function renderCards(items) {
  state.cards = items;
  const wrap = $("cards");
  wrap.innerHTML = "";
  if (!items.length) {
    wrap.innerHTML = '<div class="empty">这里还没有内容。拖拽文件到任意位置即可上传。</div>';
    return;
  }
  let lastGroup = null;
  items.forEach((doc) => {
    // 分组分隔线：按一级分类分组
    const group = doc.hidden ? "__hidden__" : (doc.category || "未分类");
    if (group !== lastGroup) {
      const divider = document.createElement("div");
      divider.className = "card-divider";
      divider.textContent = doc.hidden ? "已隐藏" : group;
      wrap.appendChild(divider);
      lastGroup = group;
    }

    const card = document.createElement("div");
    const hiddenCls = doc.hidden ? " hidden-doc" : "";
    card.className = "card" + (doc.needs_review ? " review" : "") + (doc.id === state.currentId ? " active" : "") + hiddenCls;
    card.onclick = () => showDetail(doc.id);
    const title = doc.title || doc.original_name;
    const metaBits = [
      doc.category, doc.subcategory, doc.vendor, doc.model,
    ].filter(Boolean);
    const tagsHtml = (doc.tags || []).slice(0, 6).map((t) => `<span class="tag">${escapeHtml(t)}</span>`).join("");
    const reviewBadge = doc.needs_review ? `<span class="tag warn">待确认</span>` : "";
    const hiddenBadge = doc.hidden ? `<span class="tag hidden-tag">已隐藏</span>` : "";
    card.innerHTML = `
      <p class="card-title">${escapeHtml(title)}</p>
      <div class="card-meta">${metaBits.map(escapeHtml).join(" · ") || "<em>未分类</em>"}</div>
      <div class="card-tags">${hiddenBadge}${reviewBadge}${tagsHtml}</div>
    `;
    wrap.appendChild(card);
  });
}

/* ---- 详情 ---- */
async function showDetail(id) {
  state.currentId = id;
  document.querySelectorAll(".card").forEach((c) => c.classList.remove("active"));
  try {
    const doc = await api(`/api/documents/${id}`);
    $("detail-empty").hidden = true;
    $("detail-content").hidden = false;
    $("d-title").textContent = doc.title || doc.original_name;
    $("d-doc-type").textContent = doc.doc_type || "";
    $("d-cat").textContent = [doc.category, doc.subcategory].filter(Boolean).join(" / ") || "未分类";
    $("d-vendor").textContent = doc.vendor ? `厂商: ${doc.vendor}` : "";
    $("d-model").textContent = doc.model ? `型号: ${doc.model}` : "";
    $("d-conf").textContent = doc.confidence ? `识别置信度 ${(doc.confidence * 100).toFixed(0)}%` : "";
    $("d-summary").textContent = doc.summary || "（无摘要）";
    $("d-tags").innerHTML = (doc.tags || []).map((t) => `<span class="tag">${escapeHtml(t)}</span>`).join("");

    // 预览
    const preview = $("d-preview");
    const mime = doc.mime || "";
    const url = `/file/${id}`;
    if (mime.startsWith("image/")) {
      preview.innerHTML = `<img src="${url}" alt="">`;
    } else if (mime === "application/pdf" || (doc.original_name || "").toLowerCase().endsWith(".pdf")) {
      preview.innerHTML = `<iframe src="${url}#zoom=page-width"></iframe>`;
    } else if (mime === "text/html" || /\.html?$/i.test(doc.original_name || "")) {
      preview.innerHTML = `<iframe src="${url}"></iframe>`;
    } else if (mime.startsWith("text/") || /\.(md|markdown|txt|log|csv|tsv|json)$/i.test(doc.original_name || "")) {
      preview.innerHTML = `<div class="text-preview">加载中...</div>`;
      fetch(url).then(r => r.ok ? r.text() : Promise.reject("加载失败")).then(text => {
        preview.innerHTML = `<div class="text-preview">${escapeHtml(text.slice(0, 50000))}</div>`;
      }).catch(() => {
        preview.innerHTML = `<div class="text-preview">文本加载失败</div>`;
      });
    } else {
      preview.innerHTML = `<div class="text-preview">此格式无法在网页中预览，点击右上角『下载』查看。</div>`;
    }

    document.querySelectorAll(".card").forEach((c, idx) => {
      if (state.cards[idx]?.id === id) c.classList.add("active");
    });
    // 更新隐藏按钮状态
    const hideBtn = $("d-hide");
    hideBtn.textContent = doc.hidden ? "取消隐藏" : "隐藏";
    hideBtn.title = doc.hidden ? "取消隐藏，下次同步时会上传到分享平台" : "隐藏后不会同步到分享平台";
    // 详情区隐藏状态标记
    const hiddenFlag = $("d-hidden-flag");
    hiddenFlag.hidden = !doc.hidden;
    detail._doc = doc;
  } catch (e) { toast(e.message); }
}
const detail = {};

/* ---- 编辑 ---- */
let TAXONOMY = null; // { categories: [], unclassified: "待归档" }

async function ensureTaxonomy() {
  if (TAXONOMY) return TAXONOMY;
  TAXONOMY = await api("/api/taxonomy/categories");
  // 把 5 个大类填进 <select>
  const sel = $("e-category");
  sel.innerHTML = "";
  TAXONOMY.categories.forEach((cat) => {
    const opt = document.createElement("option");
    opt.value = cat; opt.textContent = cat;
    sel.appendChild(opt);
  });
  // 大类改变时刷新细类下拉
  sel.onchange = () => refreshSubcategoryOptions(sel.value);
  return TAXONOMY;
}

async function refreshSubcategoryOptions(category) {
  const subInput = $("e-subcategory");
  const datalist = $("subcategory-options");
  datalist.innerHTML = "";
  if (!category || category === TAXONOMY?.unclassified) {
    subInput.value = "";
    subInput.disabled = true;
    subInput.placeholder = "「待归档」无细类";
    return;
  }
  subInput.disabled = false;
  subInput.placeholder = "点输入框可选已有项，也可自由输入新名";
  try {
    const { all } = await api(`/api/taxonomy/subcategories?category=${encodeURIComponent(category)}`);
    (all || []).forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s;
      datalist.appendChild(opt);
    });
  } catch (e) { /* 静默 */ }
}

async function openEdit(doc) {
  await ensureTaxonomy();

  // 当前大类如果不在 5 个枚举中（迁移残留），先临时加进 <select>
  const sel = $("e-category");
  const targetCat = doc.category || TAXONOMY.categories[0];
  if (![...sel.options].some(o => o.value === targetCat)) {
    const opt = document.createElement("option");
    opt.value = targetCat; opt.textContent = `${targetCat}（旧）`;
    sel.appendChild(opt);
  }
  sel.value = targetCat;

  await refreshSubcategoryOptions(targetCat);

  $("e-subcategory").value = doc.subcategory || "";
  $("e-vendor").value = doc.vendor || "";
  $("e-model").value = doc.model || "";
  $("e-doc_type").value = doc.doc_type || "";
  $("e-title").value = doc.title || "";
  $("e-summary").value = doc.summary || "";
  $("e-tags").value = (doc.tags || []).join(", ");
  $("modal-mask").hidden = false;
}

async function saveEdit() {
  const id = state.currentId;
  if (!id) return;
  const tags = $("e-tags").value.split(/[,，\s]+/).map((s) => s.trim()).filter(Boolean);
  const body = {
    category: $("e-category").value.trim() || null,
    subcategory: $("e-subcategory").value.trim() || null,
    vendor: $("e-vendor").value.trim() || null,
    model: $("e-model").value.trim() || null,
    doc_type: $("e-doc_type").value.trim() || null,
    title: $("e-title").value.trim() || null,
    summary: $("e-summary").value.trim() || null,
    tags,
    needs_review: false,
  };
  try {
    await api(`/api/documents/${id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    $("modal-mask").hidden = true;
    toast("已保存");
    await loadTree();
    await loadList();
    await showDetail(id);
  } catch (e) { toast(e.message); }
}

async function deleteCurrent() {
  const id = state.currentId;
  if (!id) return;
  if (!confirm("确定要删除这份资料吗？文件也会从磁盘移除。")) return;
  try {
    await api(`/api/documents/${id}`, { method: "DELETE" });
    state.currentId = null;
    $("detail-empty").hidden = false;
    $("detail-content").hidden = true;
    await loadTree(); await loadList();
    toast("已删除");
  } catch (e) { toast(e.message); }
}

/* ---- 上传（按钮 + 拖拽） ---- */
async function uploadFiles(fileList) {
  const files = Array.from(fileList || []);
  if (!files.length) return;
  // 每批拖拽 = 一张独立进度卡片，多张能叠加；不会互相覆盖
  const card = newProgressCard(`正在识别 ${files.length} 份文档 ...`);

  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  try {
    const data = await api("/api/upload", { method: "POST", body: fd });
    const okItems = data.results.filter((r) => r.ok);
    const failed = data.results.length - okItems.length;
    const warns = [...new Set(data.results.flatMap((r) => r.warnings || []))];

    const lines = [`已识别 ${okItems.length} 份${failed ? `（失败 ${failed}）` : ""}`];
    for (const r of okItems.slice(0, 5)) {
      const c = r.classification || {};
      const path = [c.category, c.subcategory, c.vendor, c.model].filter(Boolean).join(" / ");
      const tagStr = (c.tags || []).slice(0, 5).join("、");
      if (path) {
        lines.push(`• ${c.title || r.filename}\n  → ${path}${tagStr ? `  [${tagStr}]` : ""}`);
      } else {
        lines.push(`• ${r.filename} → 未识别，已放入"待归档"`);
      }
    }
    if (okItems.length > 5) lines.push(`...等共 ${okItems.length} 份`);
    if (warns.length) lines.push(`ⓘ ${warns.join("；")}`);

    updateProgressCard(card, "done", lines.join("\n"));
    card._scheduleDismiss(10000); // 10 秒后自动淺出，鼠标悬停暂停

    await loadTree(); await loadList();
    if (okItems.length) showDetail(okItems[0].id);
  } catch (e) {
    updateProgressCard(card, "error", `上传失败：${e.message}`);
    card._scheduleDismiss(10000);
  }
}

async function refreshReviewBadge() {
  try {
    const { count } = await api("/api/documents?needs_review=true&limit=1");
    const badge = $("review-count");
    badge.textContent = count;
    badge.style.display = count > 0 ? "" : "none";
  } catch {}
}

/* ---- 一键重整 ---- */
let _reorgProposal = null;

async function refreshReorgStatus() {
  try {
    const data = await api("/api/reorganize/status");
    const btn = $("btn-undo-reorg");
    if (data.has_snapshot) {
      btn.hidden = false;
      const ts = data.snapshot_saved_at || "";
      btn.title = `回退上次重整（备份于 ${ts}，含 ${data.doc_count || 0} 份文档）`;
    } else {
      btn.hidden = true;
    }
  } catch (e) { /* 静默：状态查询失败不打扰 */ }
}

async function undoReorganize() {
  if (!confirm("确定回退到上次重整前的状态吗？所有文件会迁回原位，新建的大类会消失。\n\n回退只能进行一次（成功后快照消费掉）。")) {
    return;
  }
  try {
    const data = await api("/api/reorganize/rollback", { method: "POST" });
    toast(`✓ 已回退，复原 ${data.moved_files} 份文件`);
    TAXONOMY = null;
    await loadTree();
    await loadList();
    await refreshReorgStatus();
  } catch (e) {
    toast("回退失败：" + e.message);
  }
}

async function openReorganize() {
  $("reorg-mask").hidden = false;
  $("reorg-loading").hidden = false;
  $("reorg-error").hidden = true;
  $("reorg-result").hidden = true;
  $("reorg-actions").hidden = true;
  _reorgProposal = null;
  try {
    const data = await api("/api/reorganize/preview", { method: "POST" });
    _reorgProposal = data;
    renderReorgPreview(data);
    $("reorg-loading").hidden = true;
    $("reorg-result").hidden = false;
    $("reorg-actions").hidden = false;
  } catch (e) {
    $("reorg-loading").hidden = true;
    $("reorg-error").hidden = false;
    $("reorg-error-msg").textContent = e.message;
  }
}

function renderReorgPreview(data) {
  $("reorg-rationale-text").textContent = data.rationale || "(无)";

  const curCats = data.current_categories || [];
  const newCats = data.new_categories || [];
  const added = new Set(data.diff?.categories_added || []);
  const removed = new Set(data.diff?.categories_removed || []);

  const curUl = $("reorg-cur-cats");
  curUl.innerHTML = "";
  curCats.forEach((c) => {
    const li = document.createElement("li");
    li.textContent = c;
    li.className = removed.has(c) ? "removed" : "kept";
    curUl.appendChild(li);
  });

  const newUl = $("reorg-new-cats");
  newUl.innerHTML = "";
  newCats.forEach((c) => {
    const li = document.createElement("li");
    li.textContent = c;
    li.className = added.has(c) ? "added" : "kept";
    newUl.appendChild(li);
  });

  $("reorg-moved-count").textContent = data.diff?.docs_moved_count ?? 0;
  $("reorg-total-count").textContent = data.diff?.docs_total ?? 0;

  const moves = $("reorg-moves");
  moves.innerHTML = "";
  const movedList = data.diff?.docs_moved || [];
  if (!movedList.length) {
    moves.innerHTML = '<div class="reorg-moves-empty">所有文档的位置都保持不变（AI 认为现状已经合理）</div>';
  } else {
    movedList.forEach((m) => {
      const row = document.createElement("div");
      row.className = "reorg-move-row";
      row.innerHTML = `
        <span class="title">${escapeHtml(m.title || `id=${m.doc_id}`)}</span>
        <span class="from">${escapeHtml(m.from)}</span>
        <span class="arrow">→</span>
        <span class="to">${escapeHtml(m.to)}</span>
      `;
      moves.appendChild(row);
    });
  }
}

function closeReorganize() {
  $("reorg-mask").hidden = true;
  _reorgProposal = null;
}

async function applyReorganize() {
  if (!_reorgProposal) return;
  const btn = $("reorg-apply");
  btn.disabled = true;
  btn.textContent = "应用中...";
  try {
    const data = await api("/api/reorganize/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        new_categories: _reorgProposal.new_categories,
        assignments: _reorgProposal.assignments,
      }),
    });
    const errLine = data.errors?.length ? `\n(有 ${data.errors.length} 个错误)` : "";
    toast(`✓ 重整完成，迁移 ${data.moved_files} 份文件${errLine}`, 8000);
    closeReorganize();
    // 重新加载分类常量缓存 + 树 + 列表
    TAXONOMY = null;
    await loadTree();
    await loadList();
    await refreshReorgStatus();  // 让回退按钮显现
  } catch (e) {
    toast("应用失败：" + e.message, 8000);
  } finally {
    btn.disabled = false;
    btn.textContent = "应用";
  }
}

/* ---- 隐藏 / 同步分享 ---- */
async function toggleHidden() {
  const id = state.currentId;
  if (!id || !detail._doc) return;
  const newHidden = !detail._doc.hidden;
  try {
    await api(`/api/share/documents/${id}/hidden?hidden=${newHidden}`, { method: "PUT" });
    toast(newHidden ? "已隐藏，下次同步时将从分享平台移除" : "已取消隐藏，下次同步时将上传");
    await loadList();
    await showDetail(id);
  } catch (e) { toast(e.message); }
}

async function syncShare() {
  const card = newProgressCard("正在同步到腾讯云 COS ...");
  try {
    const data = await api("/api/share/sync", { method: "POST" });
    if (data.ok) {
      const msg = `同步完成：上传 ${data.uploaded} 份，删除 ${data.deleted} 份，共享 ${data.total_shared} 份`;
      updateProgressCard(card, "done", msg);
    } else {
      const errMsg = data.error || (data.errors || []).join("；") || "未知错误";
      updateProgressCard(card, "error", `同步失败：${errMsg}`);
    }
    card._scheduleDismiss(8000);
  } catch (e) {
    updateProgressCard(card, "error", `同步失败：${e.message}`);
    card._scheduleDismiss(8000);
  }
}

/* ---- 工具 ---- */
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
}

/* ---- 事件绑定 ---- */
window.addEventListener("DOMContentLoaded", () => {
  loadTree(); setFilter({ type: "all" });

  $("btn-refresh").onclick = () => { loadTree(); loadList(); };
  $("btn-upload").onclick = () => $("file-input").click();
  $("file-input").onchange = (e) => uploadFiles(e.target.files);
  $("btn-review").onclick = () => { setFilter({ type: "review" }); };
  $("btn-sync").onclick = syncShare;
  $("btn-reorganize").onclick = openReorganize;
  $("btn-undo-reorg").onclick = undoReorganize;
  $("reorg-cancel").onclick = closeReorganize;
  $("reorg-close-x").onclick = closeReorganize;
  $("reorg-apply").onclick = applyReorganize;
  refreshReorgStatus(); // 启动时查一次，决定回退按钮显隐
  $("reorg-mask").addEventListener("click", (ev) => {
    if (ev.target === $("reorg-mask")) closeReorganize();
  });

  let searchTimer;
  $("search-input").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    const v = e.target.value.trim();
    searchTimer = setTimeout(() => {
      if (!v) { setFilter({ type: "all" }); }
      else { state.filter = { type: "search", value: v }; loadList(); }
    }, 250);
  });

  $("d-edit").onclick = () => detail._doc && openEdit(detail._doc);
  $("d-hide").onclick = toggleHidden;
  $("d-delete").onclick = deleteCurrent;
  $("d-download").onclick = () => state.currentId && window.open(`/file/${state.currentId}?download=1`);
  $("d-new-tab").onclick = () => state.currentId && window.open(`/file/${state.currentId}`, "_blank");
  $("d-open-local").onclick = async () => {
    if (!state.currentId) return;
    try {
      await api(`/api/documents/${state.currentId}/open-local`, { method: "POST" });
      toast("已用本地默认程序打开");
    } catch (e) { toast("本地打开失败：" + e.message); }
  };
  $("e-cancel").onclick = () => ($("modal-mask").hidden = true);
  $("e-save").onclick = saveEdit;
  // 点弹窗外的遮罩也能关闭
  $("modal-mask").addEventListener("click", (ev) => {
    if (ev.target === $("modal-mask")) $("modal-mask").hidden = true;
  });
  // Esc 关闭弹窗
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") $("modal-mask").hidden = true;
  });

  // 拖拽上传：全页面
  let dragCount = 0;
  const overlay = $("drop-overlay");
  window.addEventListener("dragenter", (e) => {
    if (!e.dataTransfer?.types?.includes("Files")) return;
    dragCount++; overlay.classList.add("show");
  });
  window.addEventListener("dragleave", () => { dragCount = Math.max(0, dragCount - 1); if (!dragCount) overlay.classList.remove("show"); });
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => {
    e.preventDefault(); dragCount = 0; overlay.classList.remove("show");
    if (e.dataTransfer?.files?.length) uploadFiles(e.dataTransfer.files);
  });
});
