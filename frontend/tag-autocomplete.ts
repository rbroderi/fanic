/*
 * AUTO-GENERATED OUTPUT WARNING:
 * Do not edit the generated static/*.js files directly.
 * Make changes in frontend/*.ts and rebuild.
 */

(() => {
  const FIELD_SELECTOR = "input[data-tag-autocomplete='1']";
  const MENU_CLASS = "tag-autocomplete-menu";
  const ITEM_CLASS = "tag-autocomplete-item";
  const ITEM_ACTIVE_CLASS = "tag-autocomplete-item-active";

  type TokenInfo = {
    token: string;
    tokenStart: number;
    tokenEnd: number;
  };

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
  ): Promise<void> {
    const caret = input.selectionStart !== null ? input.selectionStart : 0;
    const info = currentTokenInfo(input.value, caret);
    if (info.token.length < 1) {
      closeMenu(menu);
      return;
    }

    const type = input.dataset.tagType ? input.dataset.tagType : "";
    if (!type) {
      closeMenu(menu);
      return;
    }

    const url = new URL("/api/tag-suggestions", window.location.origin);
    url.searchParams.set("type", type);
    url.searchParams.set("q", info.token);
    url.searchParams.set("limit", "12");

    const response = await fetch(url.toString(), {
      method: "GET",
      credentials: "same-origin",
      signal: controller.signal,
    });
    if (!response.ok) {
      closeMenu(menu);
      return;
    }

    const responseType = response.headers.get("content-type");
    if (!responseType || !responseType.toLowerCase().includes("application/json")) {
      closeMenu(menu);
      return;
    }

    const payload: unknown = await response.json();
    const payloadMap = payload as { suggestions?: unknown };
    const suggestionsRaw = Array.isArray(payloadMap.suggestions) ? payloadMap.suggestions : [];
    const suggestions = suggestionsRaw.map((item) => String(item));
    renderSuggestions(input, menu, suggestions);
  }

  function attachAutocomplete(input: HTMLInputElement): void {
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
          await fetchSuggestions(input, menu, pendingController);
        } catch {
          closeMenu(menu);
        }
      }, 120);
    };

    input.addEventListener("input", requestSuggestions);
    input.addEventListener("focus", requestSuggestions);
    input.addEventListener("keydown", (event: KeyboardEvent) => {
      if (menu.hidden) {
        return;
      }
      const activeIndex = Number(menu.dataset.activeIndex ? menu.dataset.activeIndex : "-1");
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveIndex(menu, activeIndex + 1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveIndex(menu, activeIndex - 1);
      } else if (event.key === "Enter" || event.key === "Tab") {
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
        replaceCurrentToken(input, chosen.textContent ? chosen.textContent : "");
        closeMenu(menu);
      } else if (event.key === "Escape") {
        event.preventDefault();
        closeMenu(menu);
      }
    });

    input.addEventListener("blur", () => {
      window.setTimeout(() => closeMenu(menu), 120);
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
