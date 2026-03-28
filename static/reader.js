function readBootstrap() {
  const node = document.getElementById("readerBootstrap");
  if (!node || !node.textContent) {
    return null;
  }

  try {
    return JSON.parse(node.textContent);
  } catch {
    return null;
  }
}

const bootstrap = readBootstrap();

const state = {
  mode: bootstrap?.mode === "fanart" ? "fanart" : "work",
  workId: bootstrap?.work_id || "",
  pages: Array.isArray(bootstrap?.pages) ? bootstrap.pages : [],
  chapters: Array.isArray(bootstrap?.chapters) ? bootstrap.chapters : [],
  index: Number(bootstrap?.page_index) || 1,
  userId: typeof bootstrap?.user_id === "string" ? bootstrap.user_id : "anon",
  zoom: 1,
  panX: 0,
  panY: 0,
  isPanning: false,
  didPan: false,
  lastClientX: 0,
  lastClientY: 0,
};

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 3;
const ZOOM_STEP = 0.1;

const readerImage = document.getElementById("readerImage");
const counter = document.getElementById("counter");
const thumbs = document.getElementById("thumbs");
const mobileList = document.getElementById("mobileList");
const chapterSelect = document.getElementById("chapterSelect");
const zoomInBtn = document.getElementById("zoomInBtn");
const zoomOutBtn = document.getElementById("zoomOutBtn");
const zoomResetBtn = document.getElementById("zoomResetBtn");
const readerStage = document.querySelector(".reader-stage");
const bookmarkBtn = document.getElementById("bookmarkBtn");
const bookmarkDialog = document.getElementById("bookmarkDialog");
const bookmarkMessage = document.getElementById("bookmarkMessage");
const bookmarkStatus = document.getElementById("bookmarkStatus");
const bookmarkCancelBtn = document.getElementById("bookmarkCancelBtn");
const bookmarkSaveBtn = document.getElementById("bookmarkSaveBtn");
const reportImageButton = document.getElementById("reportImageButton");
const reportModal = document.getElementById("reportModal");
const reportModalCancel = document.getElementById("reportModalCancel");
const readerReportClaimedUrl = document.getElementById("readerReportClaimedUrl");
const readerReportWorkTitle = document.getElementById("readerReportWorkTitle");

function applyZoom() {
  readerImage.style.transform = `translate(${state.panX}px, ${state.panY}px) scale(${state.zoom})`;
  if (zoomResetBtn) {
    zoomResetBtn.textContent = `${Math.round(state.zoom * 100)}%`;
  }
}

function setZoom(nextZoom) {
  const clamped = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, nextZoom));
  state.zoom = Math.round(clamped * 100) / 100;
  applyZoom();
}

function zoomIn() {
  setZoom(state.zoom + ZOOM_STEP);
}

function zoomOut() {
  setZoom(state.zoom - ZOOM_STEP);
}

function resetZoom() {
  state.panX = 0;
  state.panY = 0;
  setZoom(1);
}

function startPan(event) {
  if (event.button !== 0) {
    return;
  }
  if (!(event.target instanceof HTMLElement)) {
    return;
  }
  if (event.target.closest(".reader-ui")) {
    return;
  }
  if (event.target.classList.contains("reader-hit")) {
    return;
  }

  state.isPanning = true;
  state.didPan = false;
  state.lastClientX = event.clientX;
  state.lastClientY = event.clientY;
  readerStage?.classList.add("is-panning");
  event.preventDefault();
}

function movePan(event) {
  if (!state.isPanning) {
    return;
  }
  const dx = event.clientX - state.lastClientX;
  const dy = event.clientY - state.lastClientY;
  if (dx !== 0 || dy !== 0) {
    state.panX += dx;
    state.panY += dy;
    state.didPan = true;
    applyZoom();
  }
  state.lastClientX = event.clientX;
  state.lastClientY = event.clientY;
}

function endPan() {
  if (!state.isPanning) {
    return;
  }
  state.isPanning = false;
  readerStage?.classList.remove("is-panning");
}

async function saveProgress() {
  if (!state.workId) {
    return;
  }
  await fetch(`/api/works/${state.workId}/progress?page_index=${state.index}&user_id=${state.userId}`, {
    method: "POST",
  });
}

function setBookmarkStatus(message, cssClass) {
  if (!bookmarkStatus) {
    return;
  }
  bookmarkStatus.hidden = false;
  bookmarkStatus.textContent = message;
  bookmarkStatus.className = `status-text ${cssClass}`;
}

function closeBookmarkDialog() {
  if (!bookmarkDialog) {
    return;
  }
  bookmarkDialog.hidden = true;
}

function openBookmarkDialog() {
  if (!bookmarkDialog || !bookmarkMessage) {
    return;
  }
  bookmarkDialog.hidden = false;
  bookmarkMessage.value = "";
  if (bookmarkStatus) {
    bookmarkStatus.hidden = true;
    bookmarkStatus.textContent = "";
    bookmarkStatus.className = "status-text";
  }
  bookmarkMessage.focus();
}

async function saveBookmark() {
  if (state.userId === "anon") {
    setBookmarkStatus("Login required to add bookmarks.", "error");
    return;
  }
  if (!bookmarkMessage) {
    return;
  }

  const payload = new URLSearchParams();
  payload.set("user_id", state.userId);
  payload.set("page_index", String(state.index));
  payload.set("message", bookmarkMessage.value.trim());

  const result = await fetch(`/api/works/${state.workId}/bookmark`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" },
    body: payload.toString(),
  });

  if (!result.ok) {
    const payloadObject = await result.json().catch(() => ({}));
    const detail = typeof payloadObject?.detail === "string" ? payloadObject.detail : "Unable to save bookmark.";
    setBookmarkStatus(detail, "error");
    return;
  }

  setBookmarkStatus("Bookmark saved.", "success");
  window.setTimeout(() => {
    closeBookmarkDialog();
  }, 500);
}

function updateReportFieldsForCurrentPage() {
  const page = state.pages[state.index - 1];
  if (!page) {
    return;
  }

  if (readerReportClaimedUrl && typeof page.image_url === "string") {
    readerReportClaimedUrl.value = page.image_url;
  }

  if (readerReportWorkTitle) {
    const baseTitle = typeof bootstrap?.title === "string" ? bootstrap.title.trim() : "";
    const pageTitle = typeof page.title === "string" ? page.title.trim() : "";
    if (pageTitle && baseTitle) {
      readerReportWorkTitle.value = `${baseTitle} - ${pageTitle}`;
    } else if (pageTitle) {
      readerReportWorkTitle.value = pageTitle;
    } else if (baseTitle) {
      readerReportWorkTitle.value = baseTitle;
    }
  }
}

function openReportModal() {
  if (!reportModal) {
    return;
  }
  reportModal.hidden = false;
}

function closeReportModal() {
  if (!reportModal) {
    return;
  }
  reportModal.hidden = true;
}

function renderPage(index) {
  const page = state.pages[index - 1];
  if (!page) {
    return;
  }
  state.index = index;
  state.panX = 0;
  state.panY = 0;
  readerImage.classList.remove("visible");
  readerImage.src = page.image_url;
  readerImage.onload = () => readerImage.classList.add("visible");
  counter.textContent = `Page ${state.index} / ${state.pages.length}`;
  syncChapterSelection();
  saveProgress();
  updateReportFieldsForCurrentPage();

  const near = state.pages.slice(state.index, state.index + 3);
  near.forEach((nextPage) => {
    const preload = new Image();
    preload.src = nextPage.image_url;
  });
}

function normalizedChapters() {
  return state.chapters
    .map((chapter, idx) => {
      const title = typeof chapter?.title === "string" && chapter.title.trim() ? chapter.title : `Chapter ${idx + 1}`;
      const start = Number(chapter?.start_page) || 1;
      const end = Number(chapter?.end_page) || start;
      return {
        title,
        startPage: Math.max(1, Math.min(start, state.pages.length || 1)),
        endPage: Math.max(1, Math.min(end, state.pages.length || 1)),
      };
    })
    .filter((chapter) => chapter.endPage >= chapter.startPage)
    .sort((a, b) => a.startPage - b.startPage);
}

function renderChapterSelector() {
  if (!chapterSelect) {
    return;
  }

  const chapters = normalizedChapters();
  if (!chapters.length) {
    chapterSelect.innerHTML = '<option value="1">All pages</option>';
    chapterSelect.disabled = true;
    return;
  }

  chapterSelect.disabled = false;
  chapterSelect.innerHTML = chapters
    .map((chapter) => `<option value="${chapter.startPage}">${chapter.title} (pp. ${chapter.startPage}-${chapter.endPage})</option>`)
    .join("");

  chapterSelect.addEventListener("change", () => {
    const page = Number(chapterSelect.value) || 1;
    renderPage(Math.max(1, Math.min(page, state.pages.length)));
  });
}

function syncChapterSelection() {
  if (!chapterSelect || chapterSelect.disabled) {
    return;
  }
  const chapters = normalizedChapters();
  const chapter = chapters.find((item) => state.index >= item.startPage && state.index <= item.endPage);
  if (chapter) {
    chapterSelect.value = String(chapter.startPage);
  }
}

function previousPage() {
  if (state.index > 1) {
    renderPage(state.index - 1);
  }
}

function nextPage() {
  if (state.index < state.pages.length) {
    renderPage(state.index + 1);
  }
}

function bindControls() {
  document.getElementById("prevBtn").addEventListener("click", previousPage);
  document.getElementById("nextBtn").addEventListener("click", nextPage);
  document.getElementById("hitLeft").addEventListener("click", previousPage);
  document.getElementById("hitRight").addEventListener("click", nextPage);
  zoomInBtn?.addEventListener("click", zoomIn);
  zoomOutBtn?.addEventListener("click", zoomOut);
  zoomResetBtn?.addEventListener("click", resetZoom);
  readerStage?.addEventListener("mousedown", startPan);
  window.addEventListener("mousemove", movePan);
  window.addEventListener("mouseup", endPan);
  readerStage?.addEventListener(
    "click",
    (event) => {
      if (state.didPan) {
        event.preventDefault();
        event.stopPropagation();
        state.didPan = false;
      }
    },
    true,
  );
  if (state.mode === "work") {
    bookmarkBtn?.addEventListener("click", openBookmarkDialog);
    bookmarkCancelBtn?.addEventListener("click", closeBookmarkDialog);
    bookmarkSaveBtn?.addEventListener("click", () => {
      saveBookmark();
    });
    bookmarkDialog?.addEventListener("click", (event) => {
      if (event.target === bookmarkDialog) {
        closeBookmarkDialog();
      }
    });
  }

  reportImageButton?.addEventListener("click", openReportModal);
  reportModalCancel?.addEventListener("click", closeReportModal);
  reportModal?.addEventListener("click", (event) => {
    if (event.target === reportModal) {
      closeReportModal();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (!bookmarkDialog?.hidden && event.key === "Escape") {
      event.preventDefault();
      closeBookmarkDialog();
      return;
    }
    if (reportModal && !reportModal.hidden && event.key === "Escape") {
      event.preventDefault();
      closeReportModal();
      return;
    }

    const tagName = event.target instanceof HTMLElement ? event.target.tagName : "";
    if (tagName === "INPUT" || tagName === "TEXTAREA" || tagName === "SELECT") {
      return;
    }

    if (event.key === "ArrowLeft") {
      previousPage();
    }
    if (event.key === "ArrowRight" || event.key === " ") {
      nextPage();
    }
    if (event.key === "PageUp") {
      previousPage();
    }
    if (event.key === "PageDown") {
      nextPage();
    }
    if (!event.ctrlKey && !event.metaKey) {
      if (event.key === "+" || event.key === "=") {
        event.preventDefault();
        zoomIn();
      }
      if (event.key === "-" || event.key === "_") {
        event.preventDefault();
        zoomOut();
      }
      if (event.key === "0") {
        event.preventDefault();
        resetZoom();
      }
    }
  });
}

function renderSidebar() {
  thumbs.innerHTML = state.pages
    .map(
      (page) => `<img class="thumb" src="${page.thumb_url}" alt="Page ${page.index}" data-index="${page.index}" loading="lazy" />`,
    )
    .join("");

  thumbs.querySelectorAll(".thumb").forEach((node) => {
    node.addEventListener("click", () => renderPage(Number(node.dataset.index)));
  });
}

function renderMobileList() {
  mobileList.innerHTML = state.pages
    .map(
      (page) => `<img src="${page.image_url}" alt="Page ${page.index}" loading="lazy" />`,
    )
    .join("");
}

async function init() {
  if (!state.pages.length) {
    return;
  }

  const title = typeof bootstrap?.title === "string" ? bootstrap.title : "FANIC Reader";
  document.title = `${title} - FANIC Reader`;

  const defaultWorkHref = state.workId ? `/works/${state.workId}` : "/?view=fanart";
  const workHref = typeof bootstrap?.work_href === "string" ? bootstrap.work_href : defaultWorkHref;
  const workLink = document.getElementById("workLink");
  if (workLink) {
    workLink.href = workHref;
  }

  if (state.mode !== "work") {
    if (bookmarkBtn) {
      bookmarkBtn.hidden = true;
    }
    if (bookmarkDialog) {
      bookmarkDialog.hidden = true;
    }
  }

  renderSidebar();
  renderMobileList();
  renderChapterSelector();
  applyZoom();
  bindControls();

  const initialIndex = Math.min(Math.max(state.index || 1, 1), state.pages.length || 1);
  renderPage(initialIndex);
}

init();
