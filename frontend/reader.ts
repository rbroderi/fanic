/*
 * AUTO-GENERATED OUTPUT WARNING:
 * Do not edit the generated static/*.js files directly.
 * Make changes in frontend/*.ts and rebuild.
 */

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
const MAX_CONCURRENT_MEDIA_REQUESTS = 3;
const MAX_MEDIA_RETRIES = 3;
const MEDIA_RETRY_DELAYS_MS = [250, 900, 1800];
const BLACK_PLACEHOLDER_DATA_URL =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1' height='1'%3E%3Crect width='1' height='1' fill='black'/%3E%3C/svg%3E";

const readerImage = document.getElementById("readerImage") as HTMLImageElement | null;
const counter = document.getElementById("counter") as HTMLElement | null;
const thumbs = document.getElementById("thumbs") as HTMLElement | null;
const mobileList = document.getElementById("mobileList") as HTMLElement | null;
const chapterSelect = document.getElementById("chapterSelect") as HTMLSelectElement | null;
const zoomInBtn = document.getElementById("zoomInBtn");
const zoomOutBtn = document.getElementById("zoomOutBtn");
const zoomResetBtn = document.getElementById("zoomResetBtn");
const readerStage = document.querySelector<HTMLElement>(".reader-stage");
const bookmarkBtn = document.getElementById("bookmarkBtn");
const bookmarkDialog = document.getElementById("bookmarkDialog");
const bookmarkMessage = document.getElementById("bookmarkMessage") as
  | HTMLInputElement
  | HTMLTextAreaElement
  | null;
const bookmarkStatus = document.getElementById("bookmarkStatus");
const bookmarkCancelBtn = document.getElementById("bookmarkCancelBtn");
const bookmarkSaveBtn = document.getElementById("bookmarkSaveBtn");
const reportImageButton = document.getElementById("reportImageButton");
const reportModal = document.getElementById("reportModal");
const reportModalCancel = document.getElementById("reportModalCancel");
const readerReportClaimedUrl = document.getElementById(
  "readerReportClaimedUrl",
) as HTMLInputElement | null;
const readerReportWorkTitle = document.getElementById(
  "readerReportWorkTitle",
) as HTMLInputElement | null;
let thumbObserver: IntersectionObserver | null = null;
let mobileObserver: IntersectionObserver | null = null;
let activeMediaRequests = 0;
const mediaRequestQueue: Array<() => void> = [];

function withRetryBust(url, attempt) {
  try {
    const resolved = new URL(url, window.location.href);
    resolved.searchParams.set("_retry", String(attempt));
    return resolved.toString();
  } catch {
    const separator = url.includes("?") ? "&" : "?";
    return `${url}${separator}_retry=${attempt}`;
  }
}

function scheduleMediaRequest(task: () => void, highPriority = false) {
  if (activeMediaRequests < MAX_CONCURRENT_MEDIA_REQUESTS) {
    activeMediaRequests += 1;
    task();
    return;
  }

  if (highPriority) {
    mediaRequestQueue.unshift(task);
  } else {
    mediaRequestQueue.push(task);
  }
}

function finishMediaRequest() {
  activeMediaRequests = Math.max(0, activeMediaRequests - 1);
  const nextTask = mediaRequestQueue.shift();
  if (!nextTask) {
    return;
  }
  activeMediaRequests += 1;
  nextTask();
}

function mediaClassesForNode(node) {
  if (node.classList.contains("thumb")) {
    return {
      loading: "thumb-loading",
      ready: "thumb-ready",
    };
  }

  return {
    loading: "mobile-page-loading",
    ready: "mobile-page-ready",
  };
}

function loadQueuedImage(node, highPriority = false) {
  if (!(node instanceof HTMLImageElement)) {
    return;
  }

  const source = node.dataset.src;
  if (!source) {
    return;
  }

  const stateValue = node.dataset.loadState;
  if (stateValue === "queued" || stateValue === "loading" || stateValue === "loaded") {
    return;
  }

  scheduleMediaRequest(() => {
    if (!node.isConnected) {
      finishMediaRequest();
      return;
    }

    const retryCount = Number(node.dataset.retryCount || "0");
    const requestUrl = retryCount > 0 ? withRetryBust(source, retryCount) : source;
    const stateClasses = mediaClassesForNode(node);
    node.dataset.loadState = "loading";
    node.classList.add(stateClasses.loading);

    const onLoad = () => {
      node.dataset.loaded = "1";
      node.dataset.loadState = "loaded";
      node.classList.remove(stateClasses.loading);
      node.classList.add(stateClasses.ready);
      finishMediaRequest();
    };

    const onError = () => {
      const nextRetry = retryCount + 1;
      if (nextRetry <= MAX_MEDIA_RETRIES) {
        node.dataset.retryCount = String(nextRetry);
        node.dataset.loadState = "idle";
        node.src = BLACK_PLACEHOLDER_DATA_URL;
        const delay =
          MEDIA_RETRY_DELAYS_MS[nextRetry - 1] ||
          MEDIA_RETRY_DELAYS_MS[MEDIA_RETRY_DELAYS_MS.length - 1];
        window.setTimeout(() => loadQueuedImage(node, true), delay);
      } else {
        node.dataset.loadState = "failed";
        node.src = BLACK_PLACEHOLDER_DATA_URL;
      }
      finishMediaRequest();
    };

    node.addEventListener("load", onLoad, { once: true });
    node.addEventListener("error", onError, { once: true });
    node.src = requestUrl;
  }, highPriority);

  node.dataset.loadState = "queued";
}

function loadThumbImage(node) {
  if (!(node instanceof HTMLImageElement)) {
    return;
  }
  loadQueuedImage(node, true);
}

function setupThumbProgressiveLoading() {
  if (!thumbs) {
    return;
  }

  if (thumbObserver) {
    thumbObserver.disconnect();
    thumbObserver = null;
  }

  const thumbNodes = Array.from(thumbs.querySelectorAll(".thumb"));
  if (!thumbNodes.length) {
    return;
  }

  if (!("IntersectionObserver" in window)) {
    thumbNodes.forEach(loadThumbImage);
    return;
  }

  const observer = new IntersectionObserver(
    (entries, observer) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) {
          return;
        }
        const node = entry.target;
        loadThumbImage(node);
        observer.unobserve(node);
      });
    },
    {
      root: thumbs,
      rootMargin: "90px 0px",
      threshold: 0.1,
    },
  );
  thumbObserver = observer;

  thumbNodes.forEach((node) => {
    observer.observe(node);
  });
}

function loadThumbByIndex(index) {
  if (!thumbs) {
    return;
  }
  const node = thumbs.querySelector(`.thumb[data-index="${index}"]`);
  if (node) {
    loadThumbImage(node);
  }
}

function loadMobileImage(node) {
  if (!(node instanceof HTMLImageElement)) {
    return;
  }
  loadQueuedImage(node);
}

function setupMobileProgressiveLoading() {
  if (!mobileList) {
    return;
  }

  if (mobileObserver) {
    mobileObserver.disconnect();
    mobileObserver = null;
  }

  const mobileNodes = Array.from(mobileList.querySelectorAll(".mobile-page"));
  if (!mobileNodes.length) {
    return;
  }

  if (!("IntersectionObserver" in window)) {
    mobileNodes.forEach(loadMobileImage);
    return;
  }

  const observer = new IntersectionObserver(
    (entries, observer) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) {
          return;
        }
        const node = entry.target;
        loadMobileImage(node);
        observer.unobserve(node);
      });
    },
    {
      root: null,
      rootMargin: "260px 0px",
      threshold: 0.1,
    },
  );
  mobileObserver = observer;

  mobileNodes.forEach((node) => {
    observer.observe(node);
  });
}

function applyZoom() {
  if (!readerImage) {
    return;
  }
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
  await fetch(
    `/api/comic/${state.workId}/progress?page_index=${state.index}&user_id=${state.userId}`,
    {
      method: "POST",
    },
  );
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

  const result = await fetch(`/api/comic/${state.workId}/bookmark`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" },
    body: payload.toString(),
  });

  if (!result.ok) {
    const payloadObject = await result.json().catch(() => ({}));
    const detail =
      typeof payloadObject?.detail === "string" ? payloadObject.detail : "Unable to save bookmark.";
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
  if (!readerImage || !counter) {
    return;
  }
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

  for (let offset = -1; offset <= 2; offset += 1) {
    loadThumbByIndex(state.index + offset);
  }
}

function normalizedChapters() {
  return state.chapters
    .map((chapter, idx) => {
      const title =
        typeof chapter?.title === "string" && chapter.title.trim()
          ? chapter.title
          : `Chapter ${idx + 1}`;
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
    .map(
      (chapter) =>
        `<option value="${chapter.startPage}">${chapter.title} (pp. ${chapter.startPage}-${chapter.endPage})</option>`,
    )
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
  const chapter = chapters.find(
    (item) => state.index >= item.startPage && state.index <= item.endPage,
  );
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
  document.getElementById("prevBtn")?.addEventListener("click", previousPage);
  document.getElementById("nextBtn")?.addEventListener("click", nextPage);
  document.getElementById("hitLeft")?.addEventListener("click", previousPage);
  document.getElementById("hitRight")?.addEventListener("click", nextPage);
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
  if (!thumbs) {
    return;
  }

  thumbs.innerHTML = state.pages
    .map((page) => {
      const width = Number(page.width) || 0;
      const height = Number(page.height) || 0;
      const ratioStyle =
        width > 0 && height > 0 ? ` style="--thumb-ratio: ${width} / ${height};"` : "";
      return `<img class="thumb thumb-loading" src="${BLACK_PLACEHOLDER_DATA_URL}" data-src="${page.thumb_url}" data-load-state="idle" data-retry-count="0" alt="Page ${page.index}" data-index="${page.index}" loading="lazy"${ratioStyle} />`;
    })
    .join("");

  thumbs.querySelectorAll<HTMLImageElement>(".thumb").forEach((node) => {
    node.addEventListener("click", () => renderPage(Number(node.dataset.index)));
  });

  setupThumbProgressiveLoading();
}

function renderMobileList() {
  if (!mobileList) {
    return;
  }

  mobileList.innerHTML = state.pages
    .map((page) => {
      const width = Number(page.width) || 0;
      const height = Number(page.height) || 0;
      const ratioStyle =
        width > 0 && height > 0 ? ` style="--mobile-page-ratio: ${width} / ${height};"` : "";
      return `<img class="mobile-page mobile-page-loading" src="${BLACK_PLACEHOLDER_DATA_URL}" data-src="${page.image_url}" data-load-state="idle" data-retry-count="0" alt="Page ${page.index}" loading="lazy"${ratioStyle} />`;
    })
    .join("");

  setupMobileProgressiveLoading();
}

async function init() {
  if (!state.pages.length) {
    return;
  }

  const title = typeof bootstrap?.title === "string" ? bootstrap.title : "FANIC Reader";
  document.title = `${title} - FANIC Reader`;

  const defaultWorkHref = state.workId ? `/comic/${state.workId}` : "/?view=fanart";
  const workHref = typeof bootstrap?.work_href === "string" ? bootstrap.work_href : defaultWorkHref;
  const workLink = document.getElementById("workLink") as HTMLAnchorElement | null;
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
