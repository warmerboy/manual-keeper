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

  tree.forEach((cat) => {
    const catEl = nodeEl(cat.name, cat.count);
    catEl.dataset.filterType = "category";
    catEl.dataset.filterValue = cat.name;
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

        if (sub.children?.length) {
          const venWrap = document.createElement("div");
          venWrap.className = "tree-children";
          sub.children.forEach((ven) => {
            const venEl = nodeEl(ven.name, ven.count);
            venEl.onclick = (ev) => { ev.stopPropagation(); setFilter({ type: "vendor", value: ven.name }); };
            venWrap.appendChild(venEl);
          });
          subWrap.appendChild(venWrap);
        }
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
  items.forEach((doc) => {
    const card = document.createElement("div");
    card.className = "card" + (doc.needs_review ? " review" : "") + (doc.id === state.currentId ? " active" : "");
    card.onclick = () => showDetail(doc.id);
    const title = doc.title || doc.original_name;
    const metaBits = [
      doc.category, doc.subcategory, doc.vendor, doc.model,
    ].filter(Boolean);
    const tagsHtml = (doc.tags || []).slice(0, 6).map((t) => `<span class="tag">${escapeHtml(t)}</span>`).join("");
    const reviewBadge = doc.needs_review ? `<span class="tag warn">待确认</span>` : "";
    card.innerHTML = `
      <p class="card-title">${escapeHtml(title)}</p>
      <div class="card-meta">${metaBits.map(escapeHtml).join(" · ") || "<em>未分类</em>"}</div>
      <div class="card-tags">${reviewBadge}${tagsHtml}</div>
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
    } else if (mime.startsWith("text/") || /\.(md|markdown|txt|log|csv|tsv|html?|json)$/i.test(doc.original_name || "")) {
      preview.innerHTML = `<iframe src="${url}"></iframe>`;
    } else {
      preview.innerHTML = `<div class="text-preview">此格式无法在网页中预览，点击右上角『下载』查看。</div>`;
    }

    document.querySelectorAll(".card").forEach((c, idx) => {
      if (state.cards[idx]?.id === id) c.classList.add("active");
    });
    detail._doc = doc;
  } catch (e) { toast(e.message); }
}
const detail = {};

/* ---- 编辑 ---- */
function openEdit(doc) {
  $("e-category").value = doc.category || "";
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
  toast(`正在上传 ${files.length} 个文件，AI 自动识别中 ...`, 60000);
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  try {
    const data = await api("/api/upload", { method: "POST", body: fd });
    const okItems = data.results.filter((r) => r.ok);
    const failed = data.results.length - okItems.length;
    const warns = [...new Set(data.results.flatMap((r) => r.warnings || []))];

    // 拼一份多行提示，让用户看到 AI 识别出了什么
    const lines = [`已上传 ${okItems.length} 份资料${failed ? `（失败 ${failed}）` : ""}`];
    for (const r of okItems.slice(0, 5)) {
      const c = r.classification || {};
      const path = [c.category, c.subcategory, c.vendor, c.model].filter(Boolean).join(" / ");
      const tagStr = (c.tags || []).slice(0, 5).join("、");
      if (path) {
        lines.push(`• ${c.title || r.filename}  →  ${path}${tagStr ? `  [${tagStr}]` : ""}`);
      } else {
        lines.push(`• ${r.filename}  →  未识别，已放入"待确认"`);
      }
    }
    if (okItems.length > 5) lines.push(`...等共 ${okItems.length} 份`);
    if (warns.length) lines.push(`提示：${warns.join("；")}`);
    toast(lines.join("\n"), 10000);

    await loadTree(); await loadList();
    // 自动选中最新上传的第一个文件，方便用户看到 AI 识别结果
    if (okItems.length) showDetail(okItems[0].id);
  } catch (e) { toast("上传失败：" + e.message, 8000); }
}

async function refreshReviewBadge() {
  try {
    const { count } = await api("/api/documents?needs_review=true&limit=1");
    const badge = $("review-count");
    badge.textContent = count;
    badge.style.display = count > 0 ? "" : "none";
  } catch {}
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
  $("d-delete").onclick = deleteCurrent;
  $("d-download").onclick = () => state.currentId && window.open(`/file/${state.currentId}?download=1`);
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
