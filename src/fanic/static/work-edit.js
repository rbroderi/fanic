(function () {
  const ratingSelect = document.getElementById("rating");
  if (ratingSelect && ratingSelect instanceof HTMLSelectElement) {
    let previousRating = ratingSelect.value;
    ratingSelect.addEventListener("change", () => {
      const nextRating = ratingSelect.value;
      const switchedToExplicit =
        nextRating.trim().toLowerCase() === "explicit" &&
        previousRating.trim().toLowerCase() !== "explicit";
      if (switchedToExplicit) {
        const confirmed = window.confirm(
          "Setting this work to Explicit is irreversible for normal users. Only admins can lower it later. Continue?"
        );
        if (!confirmed) {
          ratingSelect.value = previousRating;
          return;
        }
      }
      previousRating = ratingSelect.value;
    });
  }

  const galleryRoot = document.getElementById("editorPageGallery");
  if (!galleryRoot) {
    return;
  }

  const selectedPageLabel = document.getElementById("selectedPageLabel");
  const insertAfterPageIndex = document.getElementById("insertAfterPageIndex");
  const replacePageIndex = document.getElementById("replacePageIndex");
  const deletePageIndex = document.getElementById("deletePageIndex");
  const replaceSelectedButton = document.getElementById("replaceSelectedButton");
  const deleteSelectedButton = document.getElementById("deleteSelectedButton");
  const orderedFilenamesInput = document.getElementById("orderedFilenamesInput");
  const chapterMembersInput = document.getElementById("chapterMembersInput");
  const saveGalleryOrderButton = document.getElementById("saveGalleryOrderButton");
  const galleryDirtyBadge = document.getElementById("galleryDirtyBadge");

  let draggedCard = null;
  let baselineSignature = "";
  let orderIsDirty = false;

  function pageCards() {
    return Array.from(galleryRoot.querySelectorAll(".page-thumb-card"));
  }

  function updateSelectedState(card) {
    pageCards().forEach((item) => item.classList.remove("selected"));
    if (!card) {
      if (selectedPageLabel) {
        selectedPageLabel.textContent = "No page selected.";
      }
      if (insertAfterPageIndex) {
        insertAfterPageIndex.value = "";
      }
      if (replacePageIndex) {
        replacePageIndex.value = "";
      }
      if (deletePageIndex) {
        deletePageIndex.value = "";
      }
      if (replaceSelectedButton) {
        replaceSelectedButton.disabled = true;
      }
      if (deleteSelectedButton) {
        deleteSelectedButton.disabled = true;
      }
      return;
    }

    const pageIndex = card.dataset.pageIndex || "";
    card.classList.add("selected");
    if (selectedPageLabel) {
      selectedPageLabel.textContent = `Selected page ${pageIndex}.`;
    }
    if (insertAfterPageIndex) {
      insertAfterPageIndex.value = pageIndex;
    }
    if (replacePageIndex) {
      replacePageIndex.value = pageIndex;
    }
    if (deletePageIndex) {
      deletePageIndex.value = pageIndex;
    }
    refreshActionLockState();
  }

  function refreshActionLockState() {
    const selected = galleryRoot.querySelector(".page-thumb-card.selected");
    const hasSelection = Boolean(selected);

    if (replaceSelectedButton) {
      replaceSelectedButton.disabled = !hasSelection || orderIsDirty;
    }
    if (deleteSelectedButton) {
      deleteSelectedButton.disabled = !hasSelection || orderIsDirty;
    }
    if (galleryDirtyBadge) {
      galleryDirtyBadge.hidden = !orderIsDirty;
    }
  }

  function setDirtyState(isDirty) {
    orderIsDirty = isDirty;
    refreshActionLockState();
  }

  function captureGalleryState() {
    const ordered = pageCards().map((card) => card.dataset.imageFilename || "");
    const chapterMembers = {};
    const chapterSections = Array.from(
      galleryRoot.querySelectorAll(".chapter-gallery-section")
    );

    chapterSections.forEach((section) => {
      const chapterId = section.dataset.chapterId || "";
      if (!chapterId) {
        return;
      }
      const members = Array.from(
        section.querySelectorAll(".page-thumb-card")
      ).map((card) => card.dataset.imageFilename || "");
      chapterMembers[chapterId] = members.filter(Boolean);
    });

    if (orderedFilenamesInput) {
      orderedFilenamesInput.value = JSON.stringify(ordered.filter(Boolean));
    }
    if (chapterMembersInput) {
      chapterMembersInput.value = JSON.stringify(chapterMembers);
    }

    const signature = JSON.stringify({
      ordered: ordered.filter(Boolean),
      chapterMembers,
    });
    if (!baselineSignature) {
      baselineSignature = signature;
    }
    setDirtyState(signature !== baselineSignature);

    if (saveGalleryOrderButton) {
      saveGalleryOrderButton.disabled = ordered.length === 0;
    }
  }

  function bindDragAndDrop(card) {
    card.addEventListener("dragstart", () => {
      draggedCard = card;
      card.classList.add("dragging");
    });

    card.addEventListener("dragend", () => {
      card.classList.remove("dragging");
      draggedCard = null;
      captureGalleryState();
    });

    card.addEventListener("dragover", (event) => {
      event.preventDefault();
    });

    card.addEventListener("drop", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (!draggedCard || draggedCard === card) {
        return;
      }
      const rect = card.getBoundingClientRect();
      const insertAfter = event.clientY > rect.top + rect.height / 2;
      const parent = card.parentElement;
      if (!parent) {
        return;
      }
      if (insertAfter) {
        parent.insertBefore(draggedCard, card.nextElementSibling);
      } else {
        parent.insertBefore(draggedCard, card);
      }
      captureGalleryState();
    });
  }

  pageCards().forEach((card) => {
    bindDragAndDrop(card);
    card.addEventListener("click", () => updateSelectedState(card));
  });

  const grids = Array.from(galleryRoot.querySelectorAll(".page-gallery-grid"));
  grids.forEach((grid) => {
    grid.addEventListener("dragover", (event) => {
      event.preventDefault();
    });

    grid.addEventListener("drop", (event) => {
      event.preventDefault();
      if (!draggedCard) {
        return;
      }
      const target = event.target;
      if (!(target instanceof Element)) {
        grid.appendChild(draggedCard);
        captureGalleryState();
        return;
      }

      const targetCard = target.closest(".page-thumb-card");
      if (targetCard && targetCard !== draggedCard && targetCard.parentElement === grid) {
        const rect = targetCard.getBoundingClientRect();
        const insertAfter = event.clientY > rect.top + rect.height / 2;
        if (insertAfter) {
          grid.insertBefore(draggedCard, targetCard.nextElementSibling);
        } else {
          grid.insertBefore(draggedCard, targetCard);
        }
      } else {
        grid.appendChild(draggedCard);
      }
      captureGalleryState();
    });
  });

  if (saveGalleryOrderButton) {
    saveGalleryOrderButton.addEventListener("click", () => {
      // The page reload will refresh baseline state; unlock immediately for responsiveness.
      baselineSignature = orderedFilenamesInput
        ? JSON.stringify({
            ordered: JSON.parse(orderedFilenamesInput.value || "[]"),
            chapterMembers: JSON.parse(chapterMembersInput?.value || "{}"),
          })
        : baselineSignature;
      setDirtyState(false);
    });
  }

  captureGalleryState();
})();
