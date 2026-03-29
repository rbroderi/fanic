/*
 * AUTO-GENERATED OUTPUT WARNING:
 * Do not edit the generated static/*.js files directly.
 * Make changes in frontend/*.ts and rebuild.
 */

(function () {
  type IngestHistoryEntry = {
    token: string;
    stage: string;
    message: string;
    done: boolean;
    ok: boolean;
    redirect_to: string;
    updated_at: number;
    created_at: number;
  };

  const form = document.getElementById("ingestForm") as HTMLFormElement | null;
  const cbzInput = document.getElementById("cbzFile") as HTMLInputElement | null;
  const progressWrap = document.getElementById("uploadProgressWrap") as HTMLElement | null;
  const progressBar = document.getElementById("uploadProgressBar") as HTMLProgressElement | null;
  const progressText = document.getElementById("uploadProgressText") as HTMLElement | null;
  const tokenInput = form?.querySelector<HTMLInputElement>("input[name='upload_token']") || null;
  const historySection = document.getElementById("ingestHistorySection") as HTMLElement | null;
  const historyList = document.getElementById("ingestHistoryList") as HTMLElement | null;
  const clearHistoryButton = document.getElementById(
    "clearIngestHistoryButton",
  ) as HTMLButtonElement | null;

  if (!form || !cbzInput || !progressWrap || !progressBar || !progressText) {
    return;
  }

  const ingestForm = form;
  const ingestCbzInput = cbzInput;
  const ingestProgressWrap = progressWrap;
  const ingestProgressBar = progressBar;
  const ingestProgressText = progressText;

  // Keep hidden until the browser actually begins sending bytes.
  ingestProgressWrap.hidden = true;

  let activeSubmitter: HTMLButtonElement | HTMLInputElement | null = null;
  let processingTimer: number | null = null;
  let processingStep = 0;
  let processingStartedAt = 0;
  let pollTimer: number | null = null;
  let historyPollTimer: number | null = null;

  const HISTORY_STORAGE_KEY = "fanic.comic_ingest_history.v1";
  const MAX_HISTORY_ITEMS = 8;

  const PROCESSING_MESSAGES = [
    "Upload complete. Unpacking CBZ...",
    "Running moderation checks on pages...",
    "Converting page images and thumbnails...",
    "Writing draft pages to storage...",
    "Building editor result...",
  ];

  ingestForm.querySelectorAll<HTMLButtonElement>("button[type='submit']").forEach((button) => {
    button.addEventListener("click", () => {
      activeSubmitter = button;
    });
  });

  function showProgress() {
    ingestProgressWrap.hidden = false;
    ingestProgressWrap.classList.add("is-visible");
    ingestProgressBar.value = 0;
    ingestProgressText.textContent = "Starting upload...";
  }

  function setButtonsDisabled(disabled) {
    ingestForm.querySelectorAll<HTMLButtonElement>("button[type='submit']").forEach((button) => {
      button.disabled = disabled;
    });
  }

  function setProgress(percent) {
    const bounded = Math.max(0, Math.min(100, percent));
    ingestProgressBar.value = bounded;
    ingestProgressText.textContent = `Uploading... ${bounded}%`;
  }

  function stopProcessingTimer() {
    if (processingTimer) {
      window.clearInterval(processingTimer);
      processingTimer = null;
    }
  }

  function stopProgressPolling() {
    if (pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function loadHistory(): IngestHistoryEntry[] {
    if (!window.localStorage) {
      return [];
    }
    try {
      const raw = window.localStorage.getItem(HISTORY_STORAGE_KEY);
      if (!raw) {
        return [];
      }
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) {
        return [];
      }
      return parsed
        .filter(
          (item): item is Partial<IngestHistoryEntry> => Boolean(item) && typeof item === "object",
        )
        .map((item) => ({
          token: String(item.token || ""),
          stage: String(item.stage || "queued"),
          message: String(item.message || "Waiting for status..."),
          done: Boolean(item.done),
          ok: Boolean(item.ok),
          redirect_to: String(item.redirect_to || ""),
          updated_at: Number(item.updated_at || Date.now() / 1000),
          created_at: Number(item.created_at || Date.now()),
        }))
        .filter((item) => item.token.length > 0);
    } catch {
      return [];
    }
  }

  function saveHistory(history: IngestHistoryEntry[]) {
    if (!window.localStorage) {
      return;
    }
    try {
      window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(history));
    } catch {
      // Ignore local storage failures.
    }
  }

  function upsertHistoryItem(entry: IngestHistoryEntry) {
    const token = String(entry.token || "");
    if (!token) {
      return;
    }

    const history = loadHistory();
    const next = [entry];
    for (const item of history) {
      if (!item || item.token === token) {
        continue;
      }
      next.push(item);
      if (next.length >= MAX_HISTORY_ITEMS) {
        break;
      }
    }
    saveHistory(next);
    renderHistory(next);
  }

  function renderHistory(historyArg?: IngestHistoryEntry[]) {
    if (!historySection || !historyList) {
      return;
    }

    const history = historyArg || loadHistory();
    historyList.innerHTML = "";
    historySection.hidden = history.length === 0;
    if (history.length === 0) {
      return;
    }

    for (const item of history) {
      const token = String(item.token || "");
      const stage = String(item.stage || "queued");
      const message = String(item.message || "Waiting for status...");
      const done = Boolean(item.done);
      const ok = Boolean(item.ok);
      const shortToken = token.length > 12 ? `${token.slice(0, 12)}...` : token;
      let badgeVariant = "queued";
      if (done) {
        badgeVariant = ok ? "done" : "failed";
      } else if (stage === "queued") {
        badgeVariant = "queued";
      } else {
        badgeVariant = "running";
      }

      const listItem = document.createElement("li");
      listItem.className = "ingest-history-item";
      const line = document.createElement("p");
      line.className = "profile-meta ingest-history-line";

      const badge = document.createElement("span");
      badge.className = `ingest-history-badge ingest-history-badge--${badgeVariant}`;
      badge.textContent = done ? (ok ? "complete" : "failed") : stage;
      line.appendChild(badge);

      const tokenLabel = document.createElement("span");
      tokenLabel.textContent = shortToken;
      line.appendChild(tokenLabel);

      listItem.appendChild(line);

      const detail = document.createElement("p");
      detail.className = "profile-meta";
      detail.textContent = message;
      listItem.appendChild(detail);

      const redirectTo = String(item.redirect_to || "");
      if (done && ok && redirectTo) {
        const link = document.createElement("a");
        link.href = redirectTo;
        link.textContent = "Open imported comic";
        listItem.appendChild(link);
      }

      historyList.appendChild(listItem);
    }
  }

  function updateHistoryFromProgress(token: string, progress: Record<string, unknown>) {
    const previous = loadHistory().find((entry) => entry && entry.token === token);
    const entry: IngestHistoryEntry = {
      token,
      stage: String(progress.stage || ""),
      message: String(progress.message || ""),
      done: Boolean(progress.done),
      ok: Boolean(progress.ok),
      redirect_to: String(progress.redirect_to || ""),
      updated_at: Number(progress.updated_at || Date.now() / 1000),
      created_at: previous && previous.created_at ? previous.created_at : Date.now(),
    };
    upsertHistoryItem(entry);
  }

  window.addEventListener("beforeunload", () => {
    if (historyPollTimer) {
      window.clearInterval(historyPollTimer);
      historyPollTimer = null;
    }
  });

  function fetchProgress(token) {
    const url = `/api/comic-ingest/progress?token=${encodeURIComponent(token)}`;
    return window
      .fetch(url, { method: "GET", cache: "no-store" })
      .then((response) => {
        if (!response.ok) {
          return null;
        }
        return response.json();
      })
      .then((data) => {
        if (!data || !data.progress) {
          return null;
        }
        return data.progress;
      })
      .catch(() => null);
  }

  function refreshHistoryStatuses() {
    const history = loadHistory();
    const activeTokens = history
      .filter((entry) => entry && entry.token && !entry.done)
      .map((entry) => String(entry.token));
    if (activeTokens.length === 0) {
      return;
    }

    Promise.all(
      activeTokens.map((token) =>
        fetchProgress(token).then((progress) => {
          if (progress) {
            updateHistoryFromProgress(token, progress);
          }
        }),
      ),
    ).then(() => {
      renderHistory();
    });
  }

  function buildToken() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return `comic-ingest-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  }

  function startProgressPolling(token) {
    stopProgressPolling();
    if (!token) {
      return;
    }

    const poll = () => {
      fetchProgress(token)
        .then((progress) => {
          if (!progress) {
            return;
          }

          updateHistoryFromProgress(token, progress);
          const current = Number(progress.current || 0);
          const total = Number(progress.total || 0);
          const stage = String(progress.stage || "").toLowerCase();
          const message = String(progress.message || "Processing...");
          const displayMessage = stage === "queued" ? `In Queue: ${message}` : message;
          const elapsedSeconds = Math.floor((Date.now() - processingStartedAt) / 1000);

          if (total > 0) {
            ingestProgressBar.max = total;
            ingestProgressBar.value = Math.min(total, Math.max(0, current));
          } else {
            ingestProgressBar.removeAttribute("value");
          }

          ingestProgressText.textContent = `${displayMessage} (${elapsedSeconds}s)`;

          if (progress.done) {
            stopProgressPolling();
            stopProcessingTimer();

            if (progress.ok) {
              ingestProgressBar.value = 100;
              ingestProgressBar.max = 100;
              ingestProgressText.textContent = "Import complete.";
              const redirectTo = String(progress.redirect_to || "");
              if (redirectTo) {
                ingestProgressText.textContent = "Import complete. Redirecting...";
                window.location.assign(redirectTo);
                return;
              }
            }

            setButtonsDisabled(false);
          }
        })
        .catch(() => {
          // Keep UI responsive even if heartbeat endpoint is briefly unavailable.
        });
    };

    poll();
    pollTimer = window.setInterval(poll, 1200);
  }

  function startProcessingTimer() {
    stopProcessingTimer();
    stopProgressPolling();
    processingStep = 0;
    processingStartedAt = Date.now();
    ingestProgressBar.removeAttribute("value");

    const updateText = () => {
      const elapsedSeconds = Math.floor((Date.now() - processingStartedAt) / 1000);
      const message = PROCESSING_MESSAGES[processingStep % PROCESSING_MESSAGES.length];
      ingestProgressText.textContent = `${message} (${elapsedSeconds}s)`;
      processingStep += 1;
    };

    updateText();
    processingTimer = window.setInterval(updateText, 3500);
  }

  ingestForm.addEventListener("submit", (event: SubmitEvent) => {
    const hasFile = ingestCbzInput.files && ingestCbzInput.files.length > 0;
    if (!hasFile) {
      return;
    }

    event.preventDefault();
    setButtonsDisabled(true);

    const submitter = event.submitter || activeSubmitter;
    const data = new FormData(ingestForm);
    const uploadToken = buildToken();
    data.set("upload_token", uploadToken);
    if (tokenInput) {
      tokenInput.value = uploadToken;
    }

    upsertHistoryItem({
      token: uploadToken,
      stage: "queued",
      message: "Upload started",
      done: false,
      ok: false,
      redirect_to: "",
      created_at: Date.now(),
      updated_at: Date.now() / 1000,
    });

    if (submitter instanceof HTMLButtonElement || submitter instanceof HTMLInputElement) {
      data.set(submitter.name, submitter.value);
    }

    // Avoid form property shadowing by inputs named "action".
    const postUrl = ingestForm.getAttribute("action") || window.location.pathname;

    const xhr = new XMLHttpRequest();
    xhr.open("POST", postUrl, true);

    xhr.upload.addEventListener("loadstart", () => {
      showProgress();
    });

    xhr.upload.addEventListener("progress", (progressEvent) => {
      if (!progressEvent.lengthComputable) {
        if (ingestProgressWrap.hidden) {
          showProgress();
        }
        ingestProgressText.textContent = "Uploading...";
        return;
      }
      const percent = Math.round((progressEvent.loaded / progressEvent.total) * 100);
      setProgress(percent);
    });

    xhr.upload.addEventListener("load", () => {
      startProcessingTimer();
      startProgressPolling(uploadToken);
    });

    xhr.addEventListener("load", () => {
      stopProcessingTimer();
      stopProgressPolling();
      if (xhr.status >= 200 && xhr.status < 400) {
        ingestProgressBar.value = 100;
        ingestProgressBar.max = 100;
        ingestProgressText.textContent = "Upload complete. Loading result...";
        document.open();
        document.write(xhr.responseText);
        document.close();
        return;
      }
      setButtonsDisabled(false);
      ingestProgressText.textContent = "Upload failed. Please try again.";
    });

    xhr.addEventListener("error", () => {
      stopProcessingTimer();
      stopProgressPolling();
      setButtonsDisabled(false);
      ingestProgressText.textContent = "Upload failed due to a network error.";
    });

    xhr.addEventListener("abort", () => {
      stopProcessingTimer();
      stopProgressPolling();
      setButtonsDisabled(false);
      ingestProgressText.textContent = "Upload was canceled.";
    });

    xhr.send(data);
  });

  if (clearHistoryButton) {
    clearHistoryButton.addEventListener("click", () => {
      saveHistory([]);
      renderHistory([]);
    });
  }

  renderHistory();
  historyPollTimer = window.setInterval(refreshHistoryStatuses, 4000);

  const existingToken = tokenInput && tokenInput.value ? tokenInput.value.trim() : "";
  if (existingToken) {
    upsertHistoryItem({
      token: existingToken,
      stage: "queued",
      message: "Resuming existing upload",
      done: false,
      ok: false,
      redirect_to: "",
      created_at: Date.now(),
      updated_at: Date.now() / 1000,
    });
    showProgress();
    setButtonsDisabled(true);
    startProcessingTimer();
    startProgressPolling(existingToken);
  }
})();
