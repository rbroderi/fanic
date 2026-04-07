/*
 * AUTO-GENERATED OUTPUT WARNING:
 * Do not edit the generated static/*.js files directly.
 * Make changes in frontend/*.ts and rebuild.
 * FANIC_ASSET_VERSION: 20260407
 */

(function () {
  const form = document.getElementById("fanartUploadForm") as HTMLFormElement | null;
  const imageInput = document.getElementById("fanartImage") as HTMLInputElement | null;
  const progressWrap = document.getElementById("fanartUploadProgressWrap") as HTMLElement | null;
  const progressBar = document.getElementById(
    "fanartUploadProgressBar",
  ) as HTMLProgressElement | null;
  const progressText = document.getElementById("fanartUploadProgressText") as HTMLElement | null;
  const tokenInput = form?.querySelector<HTMLInputElement>("input[name='upload_token']") || null;

  if (!form || !imageInput || !progressWrap || !progressBar || !progressText || !tokenInput) {
    return;
  }

  const uploadForm = form;
  const uploadImageInput = imageInput;
  const uploadProgressWrap = progressWrap;
  const uploadProgressBar = progressBar;
  const uploadProgressText = progressText;

  uploadProgressWrap.hidden = true;

  let pollTimer: number | null = null;
  let processingTimer: number | null = null;
  let processingStep = 0;
  let processingStartedAt = 0;

  const PROCESSING_MESSAGES = [
    "Upload complete. Validating file...",
    "Running moderation checks...",
    "Saving fanart and generating media...",
    "Finishing upload...",
  ];

  function setButtonsDisabled(disabled: boolean) {
    uploadForm.querySelectorAll<HTMLButtonElement>("button[type='submit']").forEach((button) => {
      button.disabled = disabled;
    });
  }

  function showProgress() {
    uploadProgressWrap.hidden = false;
    uploadProgressWrap.classList.add("is-visible");
    uploadProgressBar.max = 100;
    uploadProgressBar.value = 0;
    uploadProgressText.textContent = "Starting upload...";
  }

  function setProgress(percent: number) {
    const bounded = Math.max(0, Math.min(100, percent));
    uploadProgressBar.max = 100;
    uploadProgressBar.value = bounded;
    uploadProgressText.textContent = `Uploading... ${bounded}%`;
  }

  function stopPolling() {
    if (pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function stopProcessingTimer() {
    if (processingTimer) {
      window.clearInterval(processingTimer);
      processingTimer = null;
    }
  }

  function buildToken() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return `fanart-ingest-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  }

  function fetchProgress(token: string) {
    const url = `/api/fanart-ingest/progress?token=${encodeURIComponent(token)}`;
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

  function startProcessingTimer() {
    stopProcessingTimer();
    processingStep = 0;
    processingStartedAt = Date.now();
    uploadProgressBar.removeAttribute("value");

    const updateText = () => {
      const elapsedSeconds = Math.floor((Date.now() - processingStartedAt) / 1000);
      const message = PROCESSING_MESSAGES[processingStep % PROCESSING_MESSAGES.length];
      uploadProgressText.textContent = `${message} (${elapsedSeconds}s)`;
      processingStep += 1;
    };

    updateText();
    processingTimer = window.setInterval(updateText, 3500);
  }

  function startPolling(token: string) {
    stopPolling();
    if (!token) {
      return;
    }

    const poll = () => {
      fetchProgress(token)
        .then((progress) => {
          if (!progress) {
            return;
          }

          const current = Number(progress.current || 0);
          const total = Number(progress.total || 0);
          const message = String(progress.message || "Processing...");
          const elapsedSeconds = Math.floor((Date.now() - processingStartedAt) / 1000);

          if (total > 0) {
            uploadProgressBar.max = total;
            uploadProgressBar.value = Math.min(total, Math.max(0, current));
          } else {
            uploadProgressBar.removeAttribute("value");
          }

          uploadProgressText.textContent = `${message} (${elapsedSeconds}s)`;

          if (progress.done) {
            stopPolling();
            stopProcessingTimer();
            if (progress.ok) {
              uploadProgressBar.max = 100;
              uploadProgressBar.value = 100;
              uploadProgressText.textContent = "Upload complete. Redirecting...";
              const redirectTo = String(progress.redirect_to || "");
              if (redirectTo) {
                window.location.assign(redirectTo);
                return;
              }
            }
            setButtonsDisabled(false);
          }
        })
        .catch(() => {
          // Keep polling through transient API hiccups.
        });
    };

    poll();
    pollTimer = window.setInterval(poll, 1200);
  }

  uploadForm.addEventListener("submit", (event) => {
    const hasFile = uploadImageInput.files && uploadImageInput.files.length > 0;
    if (!hasFile) {
      return;
    }

    event.preventDefault();
    setButtonsDisabled(true);

    const formData = new FormData(uploadForm);
    const uploadToken = buildToken();
    tokenInput.value = uploadToken;
    formData.set("upload_token", uploadToken);

    const postUrl = uploadForm.getAttribute("action") || window.location.pathname;
    const xhr = new XMLHttpRequest();
    xhr.open("POST", postUrl, true);

    xhr.upload.addEventListener("loadstart", () => {
      showProgress();
    });

    xhr.upload.addEventListener("progress", (progressEvent) => {
      if (!progressEvent.lengthComputable) {
        uploadProgressText.textContent = "Uploading...";
        return;
      }
      const percent = Math.round((progressEvent.loaded / progressEvent.total) * 100);
      setProgress(percent);
    });

    xhr.upload.addEventListener("load", () => {
      startProcessingTimer();
      startPolling(uploadToken);
    });

    xhr.addEventListener("load", () => {
      stopPolling();
      stopProcessingTimer();
      if (xhr.status >= 200 && xhr.status < 400) {
        uploadProgressBar.max = 100;
        uploadProgressBar.value = 100;
        uploadProgressText.textContent = "Upload complete. Loading result...";
        const responseUrl =
          xhr.responseURL && xhr.responseURL.trim() ? xhr.responseURL : window.location.href;
        window.location.assign(responseUrl);
        return;
      }
      setButtonsDisabled(false);
      uploadProgressText.textContent = "Upload failed. Please try again.";
    });

    xhr.addEventListener("error", () => {
      stopPolling();
      stopProcessingTimer();
      setButtonsDisabled(false);
      uploadProgressText.textContent = "Upload failed due to a network error.";
    });

    xhr.addEventListener("abort", () => {
      stopPolling();
      stopProcessingTimer();
      setButtonsDisabled(false);
      uploadProgressText.textContent = "Upload was canceled.";
    });

    xhr.send(formData);
  });
})();
