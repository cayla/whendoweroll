(function () {
  "use strict";
  try {
    if (
      document.cookie.split(";").some(function (c) {
        return c.trim().indexOf("whendoweroll_viewer_tz=") === 0;
      })
    ) {
      return;
    }
    var tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (!tz) return;
    document.cookie =
      "whendoweroll_viewer_tz=" +
      encodeURIComponent(tz) +
      ";path=/;max-age=34560000;SameSite=Lax";
    location.reload();
  } catch (e) {}
})();
