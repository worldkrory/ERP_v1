(() => {
  const toggles = document.querySelectorAll("[data-admin-mobile-toggle]");

  toggles.forEach(toggle => {
    toggle.addEventListener("click", () => {
      document.body.classList.toggle("dn-admin-menu-open");

      const isOpen = document.body.classList.contains(
        "dn-admin-menu-open"
      );

      toggles.forEach(button => {
        button.setAttribute("aria-expanded", String(isOpen));
      });
    });
  });
})();