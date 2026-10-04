(() => {
  function closeAdminMenu() {
    document.body.classList.remove("dn-admin-menu-open");

    document
      .querySelectorAll("[data-admin-menu-toggle]")
      .forEach(button => {
        button.setAttribute("aria-expanded", "false");
      });
  }

  function toggleAdminMenu() {
    const isOpen = document.body.classList.toggle("dn-admin-menu-open");

    document
      .querySelectorAll("[data-admin-menu-toggle]")
      .forEach(button => {
        button.setAttribute("aria-expanded", String(isOpen));
      });
  }

  document.addEventListener("click", event => {
    const toggle = event.target.closest("[data-admin-menu-toggle]");

    if (toggle) {
      toggleAdminMenu();
      return;
    }

    if (
      document.body.classList.contains("dn-admin-menu-open")
      && !event.target.closest(".dn-admin-sidebar")
    ) {
      closeAdminMenu();
    }
  });

  document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      closeAdminMenu();
    }
  });

  document.addEventListener("htmx:afterSwap", () => {
    closeAdminMenu();
  });
})();