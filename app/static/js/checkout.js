document.addEventListener("DOMContentLoaded", () => {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const form = document.getElementById("checkout-form");
  const steps = [...document.querySelectorAll(".fog-step")];
  const fog = document.getElementById("quote-fog");
  const panel = document.getElementById("checkout-panel");
  const paths = [...document.querySelectorAll(".toche-progress path")];
  const btn = document.getElementById("confirm-btn");
  const city = document.getElementById("ciudad_codigo");
  const label = document.getElementById("ciudad_q");

  paths.forEach((p) => {
    const len = p.getTotalLength();
    p.style.strokeDasharray = len;
    p.style.strokeDashoffset = len;
    p._len = len;
  });

  const stepDone = (s) =>
    s.dataset.step === "1"
      ? !!city.value
      : [...s.querySelectorAll("[required]")].every((i) => i.checkValidity());

  const setProgress = (ratio) => {
    paths.forEach((p, i) => {
      const local = Math.min(Math.max(ratio * paths.length - i, 0), 1);
      const to = p._len * (1 - local);
      reduce ? (p.style.strokeDashoffset = to)
             : gsap.to(p, { strokeDashoffset: to, duration: 0.8, ease: "power2.out" });
    });
    const f = { opacity: 1 - ratio * 0.85, backdropFilter: `blur(${14 - ratio * 12}px)` };
    reduce ? Object.assign(fog.style, f) : gsap.to(fog, { ...f, duration: 0.9 });
  };

  const openStep = (s) => {
    if (s.classList.contains("is-open")) return;
    s.classList.add("is-open");
    s.removeAttribute("inert");
    if (!reduce) {
      gsap.fromTo(s,
        { autoAlpha: 0, y: 28, filter: "blur(12px)" },
        { autoAlpha: 1, y: 0, filter: "blur(0px)", duration: 0.9, ease: "power3.out" });
    }
  };

  const refresh = () => {
    let done = 0;
    for (let i = 0; i < steps.length; i++) {
      if (!steps[i].classList.contains("is-open")) break;
      if (stepDone(steps[i])) {
        done++;
        if (steps[i + 1]) openStep(steps[i + 1]);
      } else break;
    }
    setProgress(done / steps.length);
    btn.disabled = done < steps.length;
  };

  steps.slice(1).forEach((s) => !reduce && gsap.set(s, { autoAlpha: 0 }));
  setProgress(0);

  form.addEventListener("input", refresh);
  form.addEventListener("keydown", (e) => {
    if (e.key === "Enter") e.preventDefault();
  });

  document.getElementById("city-results").addEventListener("click", (e) => {
    const option = e.target.closest(".city-option");
    if (!option) return;
    city.value = JSON.parse(option.getAttribute("hx-vals")).ciudad_codigo;
    label.value = option.dataset.label;
    setTimeout(() => { document.getElementById("city-results").innerHTML = ""; }, 50);
    refresh();
  });

  panel.addEventListener("pointermove", (e) => {
    const r = panel.getBoundingClientRect();
    panel.style.setProperty("--mx", `${e.clientX - r.left}px`);
    panel.style.setProperty("--my", `${e.clientY - r.top}px`);
  });

  document.body.addEventListener("htmx:afterSwap", (e) => {
    if (e.detail.target.id !== "quote-panel") return;

    quoted = true;
    gsap.killTweensOf(fog);

    if (reduce) {
        fog.style.display = "none";
        return;
    }

    const target = e.detail.target;
    const fmt = new Intl.NumberFormat("es-CO", {
        style: "currency", currency: "COP", maximumFractionDigits: 0,
    });

    const tl = gsap.timeline();
    tl.to(fog, {
        opacity: 0, backdropFilter: "blur(0px)", duration: 0.9, ease: "power2.out",
        onComplete: () => { fog.style.display = "none"; },
    });
    tl.from(target.children, { autoAlpha: 0, y: 16, stagger: 0.12, duration: 0.6 }, 0.15);

    target.querySelectorAll(".js-price").forEach((priceEl) => {
        const counter = { v: 0 };
        tl.to(counter, {
        v: Number(priceEl.dataset.value),
        duration: 1.2,
        ease: "power2.out",
        onUpdate: () => { priceEl.textContent = fmt.format(Math.round(counter.v)); },
        }, 0.3);
    });
    });


});