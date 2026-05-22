(function () {
  "use strict";

  function menuFor(root) {
    return root.querySelector("[data-bulk-dropdown-menu]");
  }

  function toggleFor(root) {
    return root.querySelector("[data-bulk-dropdown-toggle]");
  }

  function closeDropdown(root) {
    root.classList.remove("is-open");
    delete root.dataset.bulkDropdownOpen;
    var menu = menuFor(root);
    var toggle = toggleFor(root);
    if (menu) {
      menu.hidden = true;
    }
    if (toggle) {
      toggle.setAttribute("aria-expanded", "false");
    }
  }

  function openDropdown(root) {
    document.querySelectorAll("[data-bulk-dropdown].is-open").forEach(function (other) {
      if (other !== root) {
        closeDropdown(other);
      }
    });
    root.classList.add("is-open");
    var menu = menuFor(root);
    var toggle = toggleFor(root);
    if (menu) {
      menu.hidden = false;
    }
    if (toggle) {
      toggle.setAttribute("aria-expanded", "true");
    }
  }

  function toggleDropdown(root) {
    if (root.classList.contains("is-open")) {
      closeDropdown(root);
    } else {
      openDropdown(root);
    }
  }

  function initRoot(root) {
    if (root.dataset.bulkDropdownBound === "1") {
      return;
    }
    root.dataset.bulkDropdownBound = "1";

    var toggle = toggleFor(root);
    if (!toggle) {
      return;
    }

    toggle.addEventListener("click", function (e) {
      e.stopPropagation();
      toggleDropdown(root);
    });

    closeDropdown(root);
  }

  function syncExceptionsStickyTop() {
    var subnav = document.querySelector(".player-page .player-subnav");
    if (!subnav) {
      return;
    }
    document.documentElement.style.setProperty("--player-subnav-h", subnav.offsetHeight + "px");
  }

  function initToolbar() {
    document.querySelectorAll("[data-bulk-dropdown]").forEach(initRoot);
    syncExceptionsStickyTop();
  }

  window.addEventListener("resize", syncExceptionsStickyTop);

  document.addEventListener("click", function (e) {
    document.querySelectorAll("[data-bulk-dropdown].is-open").forEach(function (root) {
      if (!root.contains(e.target)) {
        closeDropdown(root);
      }
    });
  });

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") {
      return;
    }
    document.querySelectorAll("[data-bulk-dropdown].is-open").forEach(closeDropdown);
  });

  document.body.addEventListener("htmx:beforeRequest", function (e) {
    var elt = e.detail.elt;
    if (!elt || !elt.closest) {
      return;
    }
    if (elt.closest("[data-bulk-dropdown]")) {
      document.querySelectorAll("[data-bulk-dropdown].is-open").forEach(closeDropdown);
    }
  });

  document.body.addEventListener("htmx:afterSwap", function (e) {
    var target = e.detail.target;
    if (!target) {
      return;
    }
    if (
      target.id === "player-recurring-exceptions"
      || target.id === "player-exceptions-below-toolbar"
    ) {
      initToolbar();
    }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initToolbar);
  } else {
    initToolbar();
  }
})();
