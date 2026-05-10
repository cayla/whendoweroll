(function () {
  "use strict";

  var dialog = document.getElementById("admin-confirm-dialog");
  var titleEl = document.getElementById("admin-confirm-dialog-title");
  var bodyEl = document.getElementById("admin-confirm-dialog-body");
  var btnConfirm = document.getElementById("admin-confirm-dialog-confirm");
  var btnCancel = document.getElementById("admin-confirm-dialog-cancel");
  var pendingForm = null;

  var defaultConfirmLabel = "Confirm";
  var defaultCancelLabel = "Cancel";

  var confirmButtonClass = "btn px-4 py-2 text-sm";

  function closeDialog() {
    if (dialog && dialog.open) {
      dialog.close();
    }
    pendingForm = null;
  }

  function resetConfirmButton() {
    if (btnConfirm) {
      btnConfirm.className = confirmButtonClass;
    }
  }

  if (!dialog || !titleEl || !bodyEl || !btnConfirm || !btnCancel) {
    return;
  }

  btnCancel.addEventListener("click", closeDialog);

  btnConfirm.addEventListener("click", function () {
    var form = pendingForm;
    closeDialog();
    if (form && typeof form.requestSubmit === "function") {
      form.requestSubmit();
    }
  });

  dialog.addEventListener("click", function (e) {
    if (e.target === dialog) {
      closeDialog();
    }
  });

  dialog.addEventListener("close", function () {
    pendingForm = null;
    btnConfirm.textContent = defaultConfirmLabel;
    btnCancel.textContent = defaultCancelLabel;
    resetConfirmButton();
    titleEl.innerHTML = '<span class="sr-only">Confirmation</span>';
    bodyEl.innerHTML = '<span class="sr-only">Details</span>';
  });

  document.body.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-admin-confirm]");
    if (!btn || !(btn instanceof HTMLElement)) return;
    var form = btn.closest("form");
    if (!form) return;

    e.preventDefault();
    pendingForm = form;

    titleEl.textContent = btn.getAttribute("data-confirm-title") || "Confirm";
    var bodyText = btn.getAttribute("data-confirm-body");
    if (bodyText) {
      bodyEl.textContent = bodyText;
    } else {
      bodyEl.innerHTML = '<span class="sr-only">Details</span>';
    }

    var ok = btn.getAttribute("data-confirm-ok");
    btnConfirm.textContent = ok || defaultConfirmLabel;

    var cancelLabel = btn.getAttribute("data-confirm-cancel");
    btnCancel.textContent = cancelLabel || defaultCancelLabel;

    resetConfirmButton();

    dialog.showModal();
    btnConfirm.focus();
  });
})();
