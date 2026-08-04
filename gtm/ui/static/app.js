// Utilidades chicas de la UI. Nada de esto necesita un framework: es la razón
// por la que la UI no tiene build step — HTMX hace el trabajo pesado de traer
// HTML del server, esto solo maneja preferencias locales del navegador.

(function () {
  "use strict";

  const STORAGE_KEY = "gtm-ui-theme";

  function applyTheme(theme) {
    const root = document.documentElement;
    if (theme === "light" || theme === "dark") {
      root.setAttribute("data-theme", theme);
    } else {
      root.removeAttribute("data-theme");
    }
  }

  function currentTheme() {
    return localStorage.getItem(STORAGE_KEY) || "auto";
  }

  function cycleTheme() {
    const order = ["auto", "light", "dark"];
    const next = order[(order.indexOf(currentTheme()) + 1) % order.length];
    localStorage.setItem(STORAGE_KEY, next);
    applyTheme(next);
    updateToggleLabel();
  }

  function updateToggleLabel() {
    const btn = document.querySelector("[data-theme-toggle]");
    if (!btn) return;
    const labels = { auto: "Tema: auto", light: "Tema: claro", dark: "Tema: oscuro" };
    btn.textContent = labels[currentTheme()];
  }

  applyTheme(currentTheme());
  document.addEventListener("DOMContentLoaded", () => {
    updateToggleLabel();
    const btn = document.querySelector("[data-theme-toggle]");
    if (btn) btn.addEventListener("click", cycleTheme);
  });

  // Copiar-al-portapapeles para los mensajes de la cola de contacto.
  document.addEventListener("click", async (event) => {
    const trigger = event.target.closest("[data-copy-target]");
    if (!trigger) return;
    const target = document.querySelector(trigger.getAttribute("data-copy-target"));
    if (!target) return;
    try {
      await navigator.clipboard.writeText(target.textContent);
      const original = trigger.textContent;
      trigger.textContent = "Copiado";
      setTimeout(() => { trigger.textContent = original; }, 1200);
    } catch (_err) {
      // Sin permiso de portapapeles: no rompe nada, el usuario selecciona a mano.
    }
  });
})();
