const userMenuButton = document.getElementById("userMenuButton");
const userMenuPanel = document.getElementById("userMenuPanel");
const userMenuStatus = document.getElementById("userMenuStatus");
const userMenuLogin = document.getElementById("userMenuLogin");
const userMenuProfile = document.getElementById("userMenuProfile");
const userMenuLogout = document.getElementById("userMenuLogout");

const THEME_STORAGE_KEY = "fanic-theme";
const THEME_LIGHT = "light";
const THEME_DARK = "dark";

function themeToggles() {
  return Array.from(document.querySelectorAll("[data-theme-toggle]"));
}

function syncToggleLabel(toggle, isDark) {
  const labelText = toggle.parentElement
    ? toggle.parentElement.querySelector("[data-theme-toggle-text]")
    : null;
  if (labelText) {
    labelText.textContent = isDark ? "Dark mode" : "Light mode";
  }
}

function bindThemeToggle(toggle) {
  if (toggle.dataset.themeBound === "true") {
    return;
  }
  toggle.addEventListener("change", () => {
    setTheme(toggle.checked ? THEME_DARK : THEME_LIGHT);
  });
  toggle.dataset.themeBound = "true";
}

function ensureUserMenuThemeToggle() {
  if (!userMenuPanel) {
    return;
  }
  if (document.getElementById("userMenuThemeToggle")) {
    return;
  }

  const toggleRow = document.createElement("label");
  toggleRow.className = "toggle-row toggle-row-compact user-menu-theme-toggle";
  toggleRow.setAttribute("for", "userMenuThemeToggle");

  const toggleInput = document.createElement("input");
  toggleInput.id = "userMenuThemeToggle";
  toggleInput.type = "checkbox";
  toggleInput.setAttribute("role", "switch");
  toggleInput.setAttribute("aria-label", "Enable dark mode");
  toggleInput.setAttribute("data-theme-toggle", "");

  const toggleText = document.createElement("span");
  toggleText.setAttribute("data-theme-toggle-text", "");
  toggleText.textContent = "Dark mode";

  toggleRow.append(toggleInput, toggleText);

  const logoutAction = document.getElementById("userMenuLogout");
  if (logoutAction && logoutAction.parentElement === userMenuPanel) {
    userMenuPanel.insertBefore(toggleRow, logoutAction);
  } else {
    userMenuPanel.append(toggleRow);
  }
}

function ensureUserMenuNotificationLink() {
  if (!userMenuPanel || !userMenuProfile) {
    return;
  }
  if (document.getElementById("userMenuNotification")) {
    return;
  }

  const notificationLink = document.createElement("a");
  notificationLink.id = "userMenuNotification";
  notificationLink.className = "user-menu-link";
  notificationLink.href = "/user/notifications";
  notificationLink.innerHTML = '<i class="fa-regular fa-bell" aria-hidden="true"></i> Notifications';

  if (userMenuProfile.hasAttribute("hidden")) {
    notificationLink.setAttribute("hidden", "hidden");
  }

  const logoutAction = document.getElementById("userMenuLogout");
  if (logoutAction && logoutAction.parentElement === userMenuPanel) {
    userMenuPanel.insertBefore(notificationLink, logoutAction);
  } else {
    userMenuPanel.append(notificationLink);
  }
}

function ensureUserMenuFeedbackLink() {
  if (!userMenuPanel) {
    return;
  }
  if (document.getElementById("userMenuFeedback")) {
    return;
  }

  const feedbackLink = document.createElement("a");
  feedbackLink.id = "userMenuFeedback";
  feedbackLink.className = "user-menu-link";
  feedbackLink.href = "/feedback";
  feedbackLink.innerHTML = '<i class="fa-regular fa-comment-dots" aria-hidden="true"></i> Feedback';

  const profileLink = document.getElementById("userMenuProfile");
  const notificationLink = document.getElementById("userMenuNotification");
  if (notificationLink && notificationLink.parentElement === userMenuPanel) {
    userMenuPanel.insertBefore(feedbackLink, notificationLink.nextSibling);
    return;
  }
  if (profileLink && profileLink.parentElement === userMenuPanel) {
    userMenuPanel.insertBefore(feedbackLink, profileLink.nextSibling);
    return;
  }

  const logoutAction = document.getElementById("userMenuLogout");
  if (logoutAction && logoutAction.parentElement === userMenuPanel) {
    userMenuPanel.insertBefore(feedbackLink, logoutAction);
  } else {
    userMenuPanel.append(feedbackLink);
  }
}

function preferredTheme() {
  const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
  if (storedTheme === THEME_LIGHT || storedTheme === THEME_DARK) {
    return storedTheme;
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? THEME_DARK
    : THEME_LIGHT;
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const isDark = theme === THEME_DARK;
  for (const toggle of themeToggles()) {
    toggle.checked = isDark;
    syncToggleLabel(toggle, isDark);
  }
}

function setTheme(theme) {
  const resolvedTheme = theme === THEME_DARK ? THEME_DARK : THEME_LIGHT;
  window.localStorage.setItem(THEME_STORAGE_KEY, resolvedTheme);
  applyTheme(resolvedTheme);
}

function syncCustomThemeOverrideState(enabled) {
  const overrideStyle = document.getElementById("customThemeOverrides");
  if (!overrideStyle || !(overrideStyle instanceof HTMLStyleElement)) {
    return;
  }
  overrideStyle.disabled = !enabled;
}

function bindCustomThemePreferenceToggle() {
  const customThemeToggle = document.getElementById("customThemeEnabled");
  if (!customThemeToggle || !(customThemeToggle instanceof HTMLInputElement)) {
    return;
  }
  const customThemeForm = customThemeToggle.form;
  if (customThemeToggle.dataset.themeBound === "true") {
    syncCustomThemeOverrideState(customThemeToggle.checked);
    return;
  }

  syncCustomThemeOverrideState(customThemeToggle.checked);
  customThemeToggle.addEventListener("change", () => {
    syncCustomThemeOverrideState(customThemeToggle.checked);
    if (customThemeForm && customThemeForm instanceof HTMLFormElement) {
      if (typeof customThemeForm.requestSubmit === "function") {
        customThemeForm.requestSubmit();
        return;
      }
      customThemeForm.submit();
    }
  });
  customThemeToggle.dataset.themeBound = "true";
}

function bindProfileDisplayNameValidation() {
  const displayNameInput = document.getElementById("profileDisplayName");
  if (!displayNameInput || !(displayNameInput instanceof HTMLInputElement)) {
    return;
  }
  const hint = document.getElementById("profileDisplayNameHint");
  const validPattern = /^[A-Za-z0-9]+$/;

  function validateDisplayName() {
    const value = displayNameInput.value.trim();
    let message = "";
    if (!value) {
      message = "Display name is required.";
    } else if (!validPattern.test(value)) {
      message = "Display name must use only letters and numbers.";
    }

    displayNameInput.setCustomValidity(message);
    if (hint) {
      if (message) {
        hint.textContent = message;
        hint.hidden = false;
      } else {
        hint.textContent = "";
        hint.hidden = true;
      }
    }
  }

  displayNameInput.addEventListener("input", validateDisplayName);
  displayNameInput.addEventListener("blur", validateDisplayName);
  if (displayNameInput.form) {
    displayNameInput.form.addEventListener("submit", validateDisplayName);
  }
  validateDisplayName();
}

applyTheme(preferredTheme());
ensureUserMenuNotificationLink();
ensureUserMenuFeedbackLink();
ensureUserMenuThemeToggle();
for (const toggle of themeToggles()) {
  bindThemeToggle(toggle);
}
bindCustomThemePreferenceToggle();
bindProfileDisplayNameValidation();
applyTheme(preferredTheme());

if (userMenuButton && userMenuPanel && userMenuStatus && userMenuLogin && userMenuProfile && userMenuLogout) {
  function openMenu() {
    userMenuPanel.hidden = false;
    requestAnimationFrame(() => {
      userMenuPanel.classList.add("is-open");
    });
    userMenuButton.setAttribute("aria-expanded", "true");
  }

  function closeMenu() {
    userMenuPanel.classList.remove("is-open");
    userMenuButton.setAttribute("aria-expanded", "false");
    window.setTimeout(() => {
      if (userMenuButton.getAttribute("aria-expanded") === "false") {
        userMenuPanel.hidden = true;
      }
    }, 190);
  }

  userMenuButton.addEventListener("click", () => {
    const expanded = userMenuButton.getAttribute("aria-expanded") === "true";
    if (expanded) {
      closeMenu();
    } else {
      openMenu();
    }
  });

  document.addEventListener("click", (event) => {
    if (!userMenuPanel.hidden && !userMenuPanel.contains(event.target) && !userMenuButton.contains(event.target)) {
      closeMenu();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeMenu();
    }
  });
}
