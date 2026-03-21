const userMenuButton = document.getElementById("userMenuButton");
const userMenuPanel = document.getElementById("userMenuPanel");
const userMenuStatus = document.getElementById("userMenuStatus");
const userMenuLogin = document.getElementById("userMenuLogin");
const userMenuProfile = document.getElementById("userMenuProfile");
const userMenuLogout = document.getElementById("userMenuLogout");

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
