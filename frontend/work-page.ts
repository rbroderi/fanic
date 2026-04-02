/*
 * AUTO-GENERATED OUTPUT WARNING:
 * Do not edit the generated static/*.js files directly.
 * Make changes in frontend/*.ts and rebuild.
 */

(() => {
  const reportButton = document.getElementById("reportWorkButton") as HTMLButtonElement | null;
  const reportModal = document.getElementById("reportModal") as HTMLElement | null;
  const reportCancelButton = document.getElementById(
    "reportModalCancel",
  ) as HTMLButtonElement | null;

  if (reportButton && reportModal) {
    const closeReportModal = () => {
      reportModal.hidden = true;
    };

    reportButton.addEventListener("click", () => {
      reportModal.hidden = false;
    });

    if (reportCancelButton) {
      reportCancelButton.addEventListener("click", closeReportModal);
    }

    reportModal.addEventListener("click", (event) => {
      if (event.target === reportModal) {
        closeReportModal();
      }
    });
  }

  const bookmarkButton = document.getElementById("workBookmarkButton") as HTMLButtonElement | null;
  const bookmarkDialog = document.getElementById("workBookmarkDialog") as HTMLElement | null;
  const bookmarkMessageInput = document.getElementById(
    "workBookmarkMessage",
  ) as HTMLTextAreaElement | null;
  const bookmarkStatus = document.getElementById("workBookmarkStatus") as HTMLElement | null;
  const bookmarkCancel = document.getElementById("workBookmarkCancel") as HTMLButtonElement | null;
  const bookmarkSave = document.getElementById("workBookmarkSave") as HTMLButtonElement | null;

  if (!bookmarkButton || !bookmarkDialog || !bookmarkMessageInput || !bookmarkSave) {
    return;
  }

  const dialogNode: HTMLElement = bookmarkDialog;
  const messageNode: HTMLTextAreaElement = bookmarkMessageInput;
  const saveNode: HTMLButtonElement = bookmarkSave;

  function setStatus(text: string, cssClass: string): void {
    if (!bookmarkStatus) {
      return;
    }
    bookmarkStatus.hidden = false;
    bookmarkStatus.className = `status-text ${cssClass}`;
    bookmarkStatus.textContent = text;
  }

  function closeDialog(): void {
    dialogNode.hidden = true;
  }

  function openDialog(): void {
    dialogNode.hidden = false;
    messageNode.value = "";
    if (bookmarkStatus) {
      bookmarkStatus.hidden = true;
      bookmarkStatus.textContent = "";
      bookmarkStatus.className = "status-text";
    }
    messageNode.focus();
  }

  bookmarkButton.addEventListener("click", openDialog);
  if (bookmarkCancel) {
    bookmarkCancel.addEventListener("click", closeDialog);
  }

  dialogNode.addEventListener("click", (event) => {
    if (event.target === dialogNode) {
      closeDialog();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (dialogNode.hidden) {
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      closeDialog();
    }
  });

  saveNode.addEventListener("click", async () => {
    const workId = bookmarkButton.dataset.workId ? bookmarkButton.dataset.workId : "";
    const userId = bookmarkButton.dataset.userId ? bookmarkButton.dataset.userId : "";
    const pageIndex = bookmarkButton.dataset.pageIndex ? bookmarkButton.dataset.pageIndex : "1";

    if (!workId) {
      setStatus("Missing work id.", "error");
      return;
    }
    if (!userId || userId === "anon") {
      setStatus("Login required to add bookmarks.", "error");
      return;
    }

    const payload = new URLSearchParams();
    payload.set("user_id", userId);
    payload.set("page_index", pageIndex);
    payload.set("message", messageNode.value.trim());

    const result = await fetch(`/api/comic/${encodeURIComponent(workId)}/bookmark`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" },
      body: payload.toString(),
    });

    if (!result.ok) {
      let payloadObject: { detail?: unknown } = {};
      try {
        payloadObject = (await result.json()) as { detail?: unknown };
      } catch {
        payloadObject = {};
      }
      const detail =
        typeof payloadObject.detail === "string"
          ? payloadObject.detail
          : "Unable to save bookmark.";
      setStatus(detail, "error");
      return;
    }

    setStatus("Bookmark saved.", "success");
    window.setTimeout(() => {
      closeDialog();
    }, 500);
  });
})();
