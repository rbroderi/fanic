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
  await fetch(`/api/works/${state.workId}/progress?page_index=${state.index}&user_id=${state.userId}`, {
    method: "POST",
  });
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

  document.addEventListener("keydown", (event) => {
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
  if (!state.workId || !state.pages.length) {
    return;
  }

  const title = typeof bootstrap?.title === "string" ? bootstrap.title : "FANIC Reader";
  document.title = `${title} - FANIC Reader`;

  const workHref = typeof bootstrap?.work_href === "string" ? bootstrap.work_href : `/works/${state.workId}`;
  document.getElementById("workLink").href = workHref;

  renderSidebar();
  renderMobileList();
  renderChapterSelector();
  applyZoom();
  bindControls();

  const initialIndex = Math.min(Math.max(state.index || 1, 1), state.pages.length || 1);
  renderPage(initialIndex);
}

init();
