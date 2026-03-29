(function () {
  const form = document.getElementById("ingestForm");
  const cbzInput = document.getElementById("cbzFile");
  const progressWrap = document.getElementById("uploadProgressWrap");
  const progressBar = document.getElementById("uploadProgressBar");
  const progressText = document.getElementById("uploadProgressText");
  const tokenInput = form.querySelector("input[name='upload_token']");
  const historySection = document.getElementById("ingestHistorySection");
  const historyList = document.getElementById("ingestHistoryList");
  const clearHistoryButton = document.getElementById("clearIngestHistoryButton");

  if (!form || !cbzInput || !progressWrap || !progressBar || !progressText) {
    return;
  }

  // Keep hidden until the browser actually begins sending bytes.
  progressWrap.hidden = true;

  let activeSubmitter = null;
  let processingTimer = null;
  let processingStep = 0;
  let processingStartedAt = 0;
  let pollTimer = null;
  let historyPollTimer = null;

  const HISTORY_STORAGE_KEY = "fanic.comic_ingest_history.v1";
  const MAX_HISTORY_ITEMS = 8;

  const PROCESSING_MESSAGES = [
    "Upload complete. Unpacking CBZ...",
    "Running moderation checks on pages...",
    "Converting page images and thumbnails...",
    "Writing draft pages to storage...",
    "Building editor result...",
  ];

  form.querySelectorAll("button[type='submit']").forEach((button) => {
    button.addEventListener("click", () => {
      activeSubmitter = button;
    });
  });

  function showProgress() {
    progressWrap.hidden = false;
    progressWrap.classList.add("is-visible");
    progressBar.value = 0;
    progressText.textContent = "Starting upload...";
  }

  function setButtonsDisabled(disabled) {
    form.querySelectorAll("button[type='submit']").forEach((button) => {
      button.disabled = disabled;
    });
  }

  function setProgress(percent) {
    const bounded = Math.max(0, Math.min(100, percent));
    progressBar.value = bounded;
    progressText.textContent = `Uploading... ${bounded}%`;
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

  function loadHistory() {
    if (!window.localStorage) {
      return [];
    }
    try {
      const raw = window.localStorage.getItem(HISTORY_STORAGE_KEY);
      if (!raw) {
        return [];
      }
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  function saveHistory(history) {
    if (!window.localStorage) {
      return;
    }
    try {
      window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(history));
    } catch {
      // Ignore local storage failures.
    }
  }

  function upsertHistoryItem(entry) {
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

  function renderHistory(historyArg) {
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

  function updateHistoryFromProgress(token, progress) {
    const previous = loadHistory().find((entry) => entry && entry.token === token);
    const entry = {
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
          const elapsedSeconds = Math.floor(
            (Date.now() - processingStartedAt) / 1000,
          );

          if (total > 0) {
            progressBar.max = total;
            progressBar.value = Math.min(total, Math.max(0, current));
          } else {
            progressBar.removeAttribute("value");
          }

          progressText.textContent = `${displayMessage} (${elapsedSeconds}s)`;

          if (progress.done) {
            stopProgressPolling();
            stopProcessingTimer();

            if (progress.ok) {
              progressBar.value = 100;
              progressBar.max = 100;
              progressText.textContent = "Import complete.";
              const redirectTo = String(progress.redirect_to || "");
              if (redirectTo) {
                progressText.textContent = "Import complete. Redirecting...";
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
    progressBar.removeAttribute("value");

    const updateText = () => {
      const elapsedSeconds = Math.floor((Date.now() - processingStartedAt) / 1000);
      const message = PROCESSING_MESSAGES[processingStep % PROCESSING_MESSAGES.length];
      progressText.textContent = `${message} (${elapsedSeconds}s)`;
      processingStep += 1;
    };

    updateText();
    processingTimer = window.setInterval(updateText, 3500);
  }

  form.addEventListener("submit", (event) => {
    const hasFile = cbzInput.files && cbzInput.files.length > 0;
    if (!hasFile) {
      return;
    }

    event.preventDefault();
    setButtonsDisabled(true);

    const submitter = event.submitter || activeSubmitter;
    const data = new FormData(form);
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

    if (submitter && submitter.name) {
      data.set(submitter.name, submitter.value);
    }

    // Avoid form property shadowing by inputs named "action".
    const postUrl = form.getAttribute("action") || window.location.pathname;

    const xhr = new XMLHttpRequest();
    xhr.open("POST", postUrl, true);

    xhr.upload.addEventListener("loadstart", () => {
      showProgress();
    });

    xhr.upload.addEventListener("progress", (progressEvent) => {
      if (!progressEvent.lengthComputable) {
        if (progressWrap.hidden) {
          showProgress();
        }
        progressText.textContent = "Uploading...";
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
        progressBar.value = 100;
        progressBar.max = 100;
        progressText.textContent = "Upload complete. Loading result...";
        document.open();
        document.write(xhr.responseText);
        document.close();
        return;
      }
      setButtonsDisabled(false);
      progressText.textContent = "Upload failed. Please try again.";
    });

    xhr.addEventListener("error", () => {
      stopProcessingTimer();
      stopProgressPolling();
      setButtonsDisabled(false);
      progressText.textContent = "Upload failed due to a network error.";
    });

    xhr.addEventListener("abort", () => {
      stopProcessingTimer();
      stopProgressPolling();
      setButtonsDisabled(false);
      progressText.textContent = "Upload was canceled.";
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
