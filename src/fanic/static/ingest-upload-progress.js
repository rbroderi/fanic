(function () {
  const form = document.getElementById("ingestForm");
  const cbzInput = document.getElementById("cbzFile");
  const progressWrap = document.getElementById("uploadProgressWrap");
  const progressBar = document.getElementById("uploadProgressBar");
  const progressText = document.getElementById("uploadProgressText");

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

  function buildToken() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return `ingest-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  }

  function startProgressPolling(token) {
    stopProgressPolling();
    if (!token) {
      return;
    }

    const poll = () => {
      const url = `/api/ingest/progress?token=${encodeURIComponent(token)}`;
      window
        .fetch(url, { method: "GET", cache: "no-store" })
        .then((response) => {
          if (!response.ok) {
            return null;
          }
          return response.json();
        })
        .then((data) => {
          if (!data || !data.progress) {
            return;
          }

          const progress = data.progress;
          const current = Number(progress.current || 0);
          const total = Number(progress.total || 0);
          const message = String(progress.message || "Processing...");
          const elapsedSeconds = Math.floor(
            (Date.now() - processingStartedAt) / 1000,
          );

          if (total > 0) {
            progressBar.max = total;
            progressBar.value = Math.min(total, Math.max(0, current));
          } else {
            progressBar.removeAttribute("value");
          }

          progressText.textContent = `${message} (${elapsedSeconds}s)`;

          if (progress.done) {
            stopProgressPolling();
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
})();
