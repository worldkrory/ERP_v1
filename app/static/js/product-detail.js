document.addEventListener("DOMContentLoaded", () => {
  const mainImage = document.getElementById("product-main-image");
  const thumbnailButtons = document.querySelectorAll(".thumbnail-button");
  const variantInputs = document.querySelectorAll(
    ".variant-option input[type='radio']"
  );
  const selectedPrice = document.getElementById("selected-variant-price");
  const announcement = document.getElementById("storefront-announcements");
  const temperatureTabs = document.querySelectorAll(".temperature-tab");
  const temperatureStory = document.getElementById("temperature-story");

  function formatCop(value) {
    const amount = Number(value);

    if (!Number.isFinite(amount)) {
      return "Consultar";
    }

    return `$ ${amount.toLocaleString("es-CO", {
      maximumFractionDigits: 0
    })}`;
  }

  thumbnailButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (!mainImage) return;

      mainImage.src = button.dataset.imageSrc;
      mainImage.alt = button.dataset.imageAlt || "";

      thumbnailButtons.forEach((item) => {
        item.classList.toggle("is-active", item === button);
      });
    });
  });

  variantInputs.forEach((input) => {
    input.addEventListener("change", () => {
      const option = input.closest(".variant-option");

      document.querySelectorAll(".variant-option").forEach((item) => {
        item.classList.toggle("is-selected", item === option);
      });

      if (selectedPrice) {
        selectedPrice.textContent = formatCop(input.dataset.price);
      }

      if (announcement) {
        announcement.textContent =
          `Presentación seleccionada. ${input.dataset.stockLabel || ""}`;
      }
    });
  });

  const temperatureTexts = {
    hot: "Jugoso desde el primer sorbo.",
    warm: "Una pausa más seca y contemplativa.",
    cold: "La jugosidad regresa."
  };

  temperatureTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const key = tab.dataset.temperature;

      temperatureTabs.forEach((item) => {
        const isActive = item === tab;
        item.classList.toggle("is-active", isActive);
        item.setAttribute("aria-selected", String(isActive));
      });

      if (temperatureStory && temperatureTexts[key]) {
        temperatureStory.textContent = temperatureTexts[key];
      }

      if (announcement && temperatureTexts[key]) {
        announcement.textContent =
          `Explorando el perfil en temperatura ${tab.textContent.trim()}.`;
      }
    });
  });
});