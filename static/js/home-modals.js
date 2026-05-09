(function () {
  function bind(dialogId, openBtnId) {
    var dialog = document.getElementById(dialogId);
    var openBtn = document.getElementById(openBtnId);
    if (!dialog || !openBtn) return;

    openBtn.addEventListener("click", function () {
      dialog.showModal();
    });
    dialog.querySelectorAll("[data-dialog-close]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        dialog.close();
      });
    });
    dialog.addEventListener("click", function (e) {
      if (e.target === dialog) dialog.close();
    });
  }

  bind("home-dialog-create", "home-open-create");
  bind("home-dialog-restore", "home-open-restore");
})();
