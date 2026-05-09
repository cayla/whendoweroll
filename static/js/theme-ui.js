(function () {
  var KEY = 'whendoweroll_theme';
  var VALID = { light: 1, dark: 1, system: 1 };
  var sel = document.getElementById('theme-select');
  if (!sel) return;

  function readStoredMode() {
    var mode = null;
    try {
      mode = localStorage.getItem(KEY);
    } catch (e) {}
    if (mode && VALID[mode]) return mode;
    var m = document.cookie.match(
      /(?:^|; )whendoweroll_theme=(dark|light|system)(?:;|$)/
    );
    if (m && VALID[m[1]]) return m[1];
    return 'system';
  }

  function persist(mode) {
    try {
      localStorage.setItem(KEY, mode);
    } catch (e) {}
    document.cookie =
      'whendoweroll_theme=' +
      mode +
      ';path=/;max-age=31536000;SameSite=Lax';
  }

  function resolvedDark(mode) {
    if (mode === 'dark') return true;
    if (mode === 'light') return false;
    return (
      window.matchMedia &&
      window.matchMedia('(prefers-color-scheme: dark)').matches
    );
  }

  function apply(mode) {
    document.documentElement.classList.toggle('dark', resolvedDark(mode));
  }

  sel.value = readStoredMode();

  var mq =
    window.matchMedia &&
    window.matchMedia('(prefers-color-scheme: dark)');
  if (mq && mq.addEventListener) {
    mq.addEventListener('change', function () {
      if (sel.value === 'system') apply('system');
    });
  } else if (mq && mq.addListener) {
    mq.addListener(function () {
      if (sel.value === 'system') apply('system');
    });
  }

  sel.addEventListener('change', function () {
    var mode = sel.value;
    if (!VALID[mode]) mode = 'system';
    persist(mode);
    apply(mode);
  });
})();
