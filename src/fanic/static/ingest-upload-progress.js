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

  function setProgress(percent) {
    const bounded = Math.max(0, Math.min(100, percent));
    progressBar.value = bounded;
    progressText.textContent = `Uploading... ${bounded}%`;
  }

  form.addEventListener("submit", (event) => {
    const hasFile = cbzInput.files && cbzInput.files.length > 0;
    if (!hasFile) {
      return;
    }

    event.preventDefault();

    const submitter = event.submitter || activeSubmitter;
    const data = new FormData(form);
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

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 400) {
        progressBar.value = 100;
        progressText.textContent = "Upload complete. Loading result...";
        document.open();
        document.write(xhr.responseText);
        document.close();
        return;
      }
      progressText.textContent = "Upload failed. Please try again.";
    });

    xhr.addEventListener("error", () => {
      progressText.textContent = "Upload failed due to a network error.";
    });

    xhr.send(data);
  });
})();
