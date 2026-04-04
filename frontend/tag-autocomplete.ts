/*
 * AUTO-GENERATED OUTPUT WARNING:
 * Do not edit the generated static/*.js files directly.
 * Make changes in frontend/*.ts and rebuild.
 * FANIC_ASSET_VERSION: 20260404
 */

(() => {
  const FIELD_SELECTOR = "input[data-tag-autocomplete='1']";
  const CHIP_MODE_ATTR = "data-tag-chips";
  const MENU_CLASS = "tag-autocomplete-menu";
  const ITEM_CLASS = "tag-autocomplete-item";
  const ITEM_ACTIVE_CLASS = "tag-autocomplete-item-active";
  let chipEditorSequence = 0;

  type TokenInfo = {
    token: string;
    tokenStart: number;
    tokenEnd: number;
  };

  type SuggestionContext = {
    getQuery(): string;
    getTagType(): string;
    applySuggestion(name: string): void;
    focusField(): void;
    onSuggestions?(suggestions: string[]): void;
  };

  function bestSuggestionForQuery(query: string, suggestions: string[]): string | null {
    const trimmed = query.trim();
    if (!trimmed || suggestions.length === 0) {
      return null;
    }

    const queryLower = trimmed.toLowerCase();
    const ranked = suggestions
      .map((item) => {
        const itemLower = item.toLowerCase();
        if (itemLower === queryLower) {
          return { item, score: 0 };
        }
        if (itemLower.startsWith(queryLower)) {
          return { item, score: 100 + itemLower.length - queryLower.length };
        }
        const idx = itemLower.indexOf(queryLower);
        if (idx >= 0) {
          return { item, score: 200 + idx };
        }
        return { item, score: 1000 + Math.abs(itemLower.length - queryLower.length) };
      })
      .sort((a, b) => a.score - b.score);

    return ranked[0] ? ranked[0].item : null;
  }

  function parseCsv(raw: string): string[] {
    return raw
      .split(",")
      .map((part) => part.trim())
      .filter((part) => part.length > 0);
  }

  function uniquePreserveOrder(values: string[]): string[] {
    const seen = new Set<string>();
    const result: string[] = [];
    values.forEach((value) => {
      const key = value.toLowerCase();
      if (seen.has(key)) {
        return;
      }
      seen.add(key);
      result.push(value);
    });
    return result;
  }

  function currentTokenInfo(value: string, caret: number): TokenInfo {
    const before = value.slice(0, caret);
    const splitAt = before.lastIndexOf(",");
    const tokenStart = splitAt >= 0 ? splitAt + 1 : 0;
    const tokenRaw = value.slice(tokenStart, caret);
    const token = tokenRaw.trim();
    return { token, tokenStart, tokenEnd: caret };
  }

  function replaceCurrentToken(input: HTMLInputElement, suggestion: string): void {
    const start = input.selectionStart !== null ? input.selectionStart : 0;
    const end = input.selectionEnd !== null ? input.selectionEnd : start;
    const info = currentTokenInfo(input.value, start);

    const head = input.value.slice(0, info.tokenStart).replace(/\s*$/, "");
    const tail = input.value.slice(end);
    const needsComma = head.length > 0;
    const prefix = needsComma ? `${head}, ` : "";
    const suffix = tail.trimStart().length > 0 ? tail : ", ";

    input.value = `${prefix}${suggestion}${suffix}`;
    const newPos = (prefix + suggestion + ", ").length;
    input.setSelectionRange(newPos, newPos);
  }

  function closeMenu(menu: HTMLDivElement): void {
    menu.innerHTML = "";
    menu.hidden = true;
    menu.dataset.activeIndex = "-1";
  }

  function openMenu(menu: HTMLDivElement): void {
    menu.hidden = false;
  }

  function setActiveIndex(menu: HTMLDivElement, index: number): void {
    const items = Array.from(menu.querySelectorAll<HTMLButtonElement>(`.${ITEM_CLASS}`));
    if (items.length === 0) {
      menu.dataset.activeIndex = "-1";
      return;
    }
    let resolved = index;
    if (resolved < 0) {
      resolved = items.length - 1;
    }
    if (resolved >= items.length) {
      resolved = 0;
    }
    menu.dataset.activeIndex = String(resolved);
    items.forEach((item, idx) => {
      if (idx === resolved) {
        item.classList.add(ITEM_ACTIVE_CLASS);
        item.scrollIntoView({ block: "nearest" });
      } else {
        item.classList.remove(ITEM_ACTIVE_CLASS);
      }
    });
  }

  function renderSuggestions(
    input: HTMLInputElement,
    menu: HTMLDivElement,
    suggestions: string[],
  ): void {
    if (suggestions.length === 0) {
      closeMenu(menu);
      return;
    }

    menu.innerHTML = "";
    suggestions.forEach((name) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = ITEM_CLASS;
      item.textContent = String(name);
      item.addEventListener("mousedown", (event: MouseEvent) => {
        event.preventDefault();
        replaceCurrentToken(input, String(name));
        closeMenu(menu);
        input.focus();
      });
      menu.appendChild(item);
    });

    openMenu(menu);
    setActiveIndex(menu, 0);
  }

  async function fetchSuggestions(
    input: HTMLInputElement,
    menu: HTMLDivElement,
    controller: AbortController,
    context: SuggestionContext,
  ): Promise<void> {
    const query = context.getQuery().trim();
    if (query.length < 1) {
      if (context.onSuggestions) {
        context.onSuggestions([]);
      }
      closeMenu(menu);
      return;
    }

    const type = context.getTagType().trim();
    if (!type) {
      if (context.onSuggestions) {
        context.onSuggestions([]);
      }
      closeMenu(menu);
      return;
    }

    const url = new URL("/api/tag-suggestions", window.location.origin);
    url.searchParams.set("type", type);
    url.searchParams.set("q", query);
    url.searchParams.set("limit", "12");

    const response = await fetch(url.toString(), {
      method: "GET",
      credentials: "same-origin",
      signal: controller.signal,
    });
    if (!response.ok) {
      if (context.onSuggestions) {
        context.onSuggestions([]);
      }
      closeMenu(menu);
      return;
    }

    const responseType = response.headers.get("content-type");
    if (!responseType || !responseType.toLowerCase().includes("application/json")) {
      if (context.onSuggestions) {
        context.onSuggestions([]);
      }
      closeMenu(menu);
      return;
    }

    const payload: unknown = await response.json();
    const payloadMap = payload as { suggestions?: unknown };
    const suggestionsRaw = Array.isArray(payloadMap.suggestions) ? payloadMap.suggestions : [];
    const suggestions = suggestionsRaw.map((item) => String(item));
    if (context.onSuggestions) {
      context.onSuggestions(suggestions);
    }
    if (suggestions.length === 0) {
      closeMenu(menu);
      return;
    }

    menu.innerHTML = "";
    suggestions.forEach((name) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = ITEM_CLASS;
      item.textContent = name;
      item.addEventListener("mousedown", (event: MouseEvent) => {
        event.preventDefault();
        context.applySuggestion(name);
        closeMenu(menu);
        context.focusField();
      });
      menu.appendChild(item);
    });

    openMenu(menu);
    setActiveIndex(menu, 0);
  }

  function wireSuggestionMenu(
    input: HTMLInputElement,
    menu: HTMLDivElement,
    context: SuggestionContext,
    onEnterWithoutMenu?: () => void,
  ): void {
    let pendingController: AbortController | null = null;
    let debounceTimer: number | null = null;

    const requestSuggestions = (): void => {
      if (debounceTimer !== null) {
        window.clearTimeout(debounceTimer);
      }
      debounceTimer = window.setTimeout(async () => {
        if (pendingController) {
          pendingController.abort();
        }
        pendingController = new AbortController();
        try {
          await fetchSuggestions(input, menu, pendingController, context);
        } catch {
          closeMenu(menu);
        }
      }, 120);
    };

    input.addEventListener("input", requestSuggestions);
    input.addEventListener("focus", requestSuggestions);
    input.addEventListener("keydown", (event: KeyboardEvent) => {
      if (!menu.hidden) {
        const activeIndex = Number(menu.dataset.activeIndex ? menu.dataset.activeIndex : "-1");
        if (event.key === "ArrowDown") {
          event.preventDefault();
          setActiveIndex(menu, activeIndex + 1);
          return;
        }
        if (event.key === "ArrowUp") {
          event.preventDefault();
          setActiveIndex(menu, activeIndex - 1);
          return;
        }
        if (event.key === "Enter" || event.key === "Tab") {
          const items = Array.from(menu.querySelectorAll<HTMLButtonElement>(`.${ITEM_CLASS}`));
          if (items.length === 0) {
            return;
          }
          const idx = activeIndex >= 0 ? activeIndex : 0;
          const chosen = items[idx];
          if (!chosen) {
            return;
          }
          event.preventDefault();
          context.applySuggestion(chosen.textContent ? chosen.textContent : "");
          closeMenu(menu);
          return;
        }
        if (event.key === "Escape") {
          event.preventDefault();
          closeMenu(menu);
          return;
        }
      }

      if (event.key === "Enter" && onEnterWithoutMenu) {
        onEnterWithoutMenu();
      }
    });

    input.addEventListener("blur", () => {
      window.setTimeout(() => closeMenu(menu), 120);
    });
  }

  function attachAutocomplete(input: HTMLInputElement): void {
    const chipMode = input.getAttribute(CHIP_MODE_ATTR) === "1";
    input.setAttribute("autocomplete", "off");
    input.setAttribute("autocapitalize", "off");
    input.setAttribute("autocorrect", "off");
    input.spellcheck = false;

    const wrapper = document.createElement("div");
    wrapper.className = "tag-autocomplete-wrap";
    input.parentNode?.insertBefore(wrapper, input);
    wrapper.appendChild(input);

    const menu = document.createElement("div");
    menu.className = MENU_CLASS;
    menu.hidden = true;
    menu.dataset.activeIndex = "-1";
    wrapper.appendChild(menu);

    if (chipMode) {
      input.removeAttribute("list");
      input.hidden = true;
      const chipEditor = document.createElement("input");
      chipEditor.type = "text";
      chipEditor.className = "tag-chip-editor";
      const sourceId = input.id ? input.id : input.name;
      const sourceStem = sourceId ? sourceId : `tag-chip-${chipEditorSequence}`;
      chipEditorSequence += 1;
      chipEditor.id = `${sourceStem}-chip-editor`;
      chipEditor.name = `${sourceStem}-chip-editor-ui`;
      chipEditor.placeholder = input.placeholder;
      chipEditor.setAttribute("autocomplete", "new-password");
      chipEditor.setAttribute("autocapitalize", "off");
      chipEditor.setAttribute("autocorrect", "off");
      chipEditor.spellcheck = false;

      const parentForm = input.form;
      if (parentForm) {
        parentForm.addEventListener("submit", () => {
          chipEditor.disabled = true;
        });
      }

      const chipList = document.createElement("div");
      chipList.className = "tag-chip-list";
      wrapper.insertBefore(chipList, menu);

      const values = uniquePreserveOrder(parseCsv(input.value));
      let latestSuggestions: string[] = [];

      const syncHidden = (): void => {
        input.value = values.join(", ");
      };

      const renderChips = (): void => {
        chipList.innerHTML = "";
        values.forEach((value, index) => {
          const chip = document.createElement("button");
          chip.type = "button";
          chip.className = "tag-chip";
          chip.setAttribute("aria-label", `Remove ${value}`);
          const label = document.createElement("span");
          label.className = "tag-chip-label";
          label.textContent = value;

          const remove = document.createElement("span");
          remove.className = "tag-chip-remove";
          remove.setAttribute("aria-hidden", "true");
          remove.textContent = "x";
          const icon = document.createElement("i");
          icon.className = "fa-solid fa-xmark";
          remove.appendChild(icon);

          remove.addEventListener("click", (event: MouseEvent) => {
            event.preventDefault();
            event.stopPropagation();
            values.splice(index, 1);
            syncHidden();
            renderChips();
            chipEditor.focus();
          });

          chip.appendChild(label);
          chip.appendChild(remove);
          chip.addEventListener("click", () => {
            values.splice(index, 1);
            syncHidden();
            renderChips();
            chipEditor.focus();
          });
          chipList.appendChild(chip);
        });
        chipList.appendChild(chipEditor);
      };

      const addValue = (raw: string): void => {
        const normalized = raw.trim();
        if (!normalized) {
          return;
        }
        if (values.some((existing) => existing.toLowerCase() === normalized.toLowerCase())) {
          chipEditor.value = "";
          return;
        }
        values.push(normalized);
        syncHidden();
        chipEditor.value = "";
        renderChips();
      };

      const addClosestValue = (raw: string): void => {
        const normalized = raw.trim();
        if (!normalized) {
          return;
        }
        const chosen = bestSuggestionForQuery(normalized, latestSuggestions);
        if (!chosen) {
          return;
        }
        addValue(chosen);
      };

      chipEditor.addEventListener("keydown", (event: KeyboardEvent) => {
        if (
          event.key === "Backspace" &&
          chipEditor.value.trim().length === 0 &&
          values.length > 0
        ) {
          values.pop();
          syncHidden();
          renderChips();
          event.preventDefault();
          return;
        }

        if (event.key === "Enter" || event.key === ",") {
          event.preventDefault();
          addClosestValue(chipEditor.value);
          closeMenu(menu);
        }
      });

      chipEditor.addEventListener("paste", () => {
        window.setTimeout(() => {
          const pasted = chipEditor.value;
          if (pasted.includes(",")) {
            parseCsv(pasted).forEach((value) => addClosestValue(value));
            chipEditor.value = "";
            closeMenu(menu);
          }
        }, 0);
      });

      wireSuggestionMenu(
        chipEditor,
        menu,
        {
          getQuery(): string {
            return chipEditor.value;
          },
          getTagType(): string {
            return input.dataset.tagType ? input.dataset.tagType : "";
          },
          applySuggestion(name: string): void {
            addValue(name);
          },
          focusField(): void {
            chipEditor.focus();
          },
          onSuggestions(suggestions: string[]): void {
            latestSuggestions = suggestions;
          },
        },
        () => addClosestValue(chipEditor.value),
      );

      syncHidden();
      renderChips();
      return;
    }

    wireSuggestionMenu(input, menu, {
      getQuery(): string {
        const caret = input.selectionStart !== null ? input.selectionStart : 0;
        return currentTokenInfo(input.value, caret).token;
      },
      getTagType(): string {
        return input.dataset.tagType ? input.dataset.tagType : "";
      },
      applySuggestion(name: string): void {
        replaceCurrentToken(input, name);
      },
      focusField(): void {
        input.focus();
      },
    });
  }

  function init(): void {
    const fields = Array.from(document.querySelectorAll<HTMLInputElement>(FIELD_SELECTOR));
    fields.forEach((field) => attachAutocomplete(field));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
