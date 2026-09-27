document.addEventListener("DOMContentLoaded", () => {
  const flashes = document.querySelectorAll(".flash");

  flashes.forEach((flash) => {
    window.setTimeout(() => {
      flash.remove();
    }, 5500);
  });
});