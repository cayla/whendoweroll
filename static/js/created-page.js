(function () {
  "use strict";

  /** @param {string} cell */
  function escapeCsvField(cell) {
    const s = String(cell ?? "");
    if (/[",\n\r]/.test(s)) {
      return `"${s.replace(/"/g, '""')}"`;
    }
    return s;
  }

  /**
   * @param {{ link_type: string, link_description: string, link: string }[]} rows
   */
  function buildCsv(rows) {
    const header = ["Link Type", "Link Description", "Link"];
    const lines = [
      header.map(escapeCsvField).join(","),
      ...rows.map((r) =>
        [r.link_type, r.link_description, r.link].map(escapeCsvField).join(",")
      ),
    ];
    return "\ufeff" + lines.join("\r\n");
  }

  /**
   * @param {string} message
   */
  function announce(message) {
    const el = document.getElementById("created-page-status");
    if (el) {
      el.textContent = message;
      window.setTimeout(() => {
        if (el.textContent === message) {
          el.textContent = "";
        }
      }, 3500);
    }
  }

  function hideAllCopyToasts() {
    document.querySelectorAll(".created-copy-toast").forEach((toast) => {
      toast.classList.remove("is-visible");
      toast.classList.add("hidden");
      toast.setAttribute("aria-hidden", "true");
      const tid = toast.dataset.hideTid;
      if (tid) {
        window.clearTimeout(Number(tid));
        delete toast.dataset.hideTid;
      }
    });
  }

  /**
   * @param {HTMLButtonElement} btn
   */
  function showCopyToast(btn) {
    const wrap = btn.closest(".created-copy-wrap");
    const toast = wrap?.querySelector(".created-copy-toast");
    if (!toast || !(toast instanceof HTMLElement)) return;

    hideAllCopyToasts();

    toast.classList.remove("hidden");
    toast.setAttribute("aria-hidden", "false");
    window.requestAnimationFrame(() => {
      toast.classList.add("is-visible");
    });

    const prev = toast.dataset.hideTid;
    if (prev) window.clearTimeout(Number(prev));

    toast.dataset.hideTid = String(
      window.setTimeout(() => {
        toast.classList.remove("is-visible");
        toast.setAttribute("aria-hidden", "true");
        window.setTimeout(() => {
          toast.classList.add("hidden");
        }, 200);
        delete toast.dataset.hideTid;
      }, 2000)
    );
  }

  /**
   * @param {string} inputId
   */
  async function copyUrl(inputId) {
    const input = document.getElementById(inputId);
    if (!input || !(input instanceof HTMLInputElement)) return;
    const url = input.value;
    if (!url) return;

    try {
      await navigator.clipboard.writeText(url);
    } catch {
      input.focus();
      input.select();
      try {
        document.execCommand("copy");
      } catch {
        announce("Could not copy. Select the URL and copy manually.");
        return;
      }
    }

    const btn = Array.from(document.querySelectorAll(".created-copy-btn")).find(
      (b) => b.getAttribute("data-copy-target") === inputId
    );
    if (btn && btn instanceof HTMLButtonElement) {
      showCopyToast(btn);

      const copyIcon = btn.querySelector(".created-copy-icon");
      const doneIcon = btn.querySelector(".created-copy-done");
      if (
        copyIcon &&
        doneIcon &&
        copyIcon instanceof SVGElement &&
        doneIcon instanceof SVGElement
      ) {
        copyIcon.classList.add("hidden");
        doneIcon.classList.remove("hidden");
      }
      btn.disabled = true;
      window.setTimeout(() => {
        if (copyIcon && doneIcon) {
          copyIcon.classList.remove("hidden");
          doneIcon.classList.add("hidden");
        }
        btn.disabled = false;
      }, 2000);
    }
  }

  function parseManifest() {
    const el = document.getElementById("created-links-manifest");
    if (!el || !el.textContent) return null;
    try {
      return JSON.parse(el.textContent);
    } catch {
      return null;
    }
  }

  function downloadCsv() {
    const data = parseManifest();
    if (!data || !Array.isArray(data.rows)) {
      announce("Could not build CSV.");
      return;
    }
    const csv = buildCsv(data.rows);
    const stub = data.filename_stub || "campaign";
    const pid = data.public_id || "campaign";
    const shortId = typeof pid === "string" && pid.length >= 8 ? pid.slice(0, 8) : pid;
    const filename = `${stub}-${shortId}-links.csv`;

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    announce("CSV download started.");
  }

  document.querySelectorAll(".created-copy-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-copy-target");
      if (id) copyUrl(id);
    });
  });

  const dl = document.getElementById("created-download-csv");
  if (dl) {
    dl.addEventListener("click", downloadCsv);
  }
})();
