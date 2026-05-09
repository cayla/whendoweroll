(function () {
  var KEY = 'whendoweroll_theme';
  var COOKIE_RE = /(?:^|; )whendoweroll_theme=(dark|light|system)(?:;|$)/;
  var VALID = { light: 1, dark: 1, system: 1 };
  var mode = null;
  try {
    mode = localStorage.getItem(KEY);
  } catch (e) {}
  if (!mode || !VALID[mode]) {
    var m = document.cookie.match(COOKIE_RE);
    mode = m && VALID[m[1]] ? m[1] : 'system';
  }
  var dark =
    mode === 'dark' ||
    (mode === 'system' &&
      window.matchMedia &&
      window.matchMedia('(prefers-color-scheme: dark)').matches);
  if (dark) document.documentElement.classList.add('dark');
})();
