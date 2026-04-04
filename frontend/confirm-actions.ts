/*
 * AUTO-GENERATED OUTPUT WARNING:
 * Do not edit the generated static/*.js files directly.
 * Make changes in frontend/*.ts and rebuild.
 * FANIC_ASSET_VERSION: 20260404
 */

(() => {
  function confirmMessageFor(element: HTMLElement | null): string {
    if (!element) {
      return "";
    }
    return element.dataset.confirmMessage ? element.dataset.confirmMessage.trim() : "";
  }

  function wireForm(form: HTMLFormElement): void {
    form.addEventListener("submit", (event) => {
      const message = confirmMessageFor(form);
      if (!message) {
        return;
      }
      if (!window.confirm(message)) {
        event.preventDefault();
      }
    });
  }

  function wireButton(button: HTMLButtonElement): void {
    button.addEventListener("click", (event) => {
      const message = confirmMessageFor(button);
      if (!message) {
        return;
      }
      if (!window.confirm(message)) {
        event.preventDefault();
      }
    });
  }

  function init(): void {
    const forms = Array.from(
      document.querySelectorAll<HTMLFormElement>("form[data-confirm-message]"),
    );
    forms.forEach((form) => wireForm(form));

    const buttons = Array.from(
      document.querySelectorAll<HTMLButtonElement>("button[data-confirm-message]"),
    );
    buttons.forEach((button) => wireButton(button));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
