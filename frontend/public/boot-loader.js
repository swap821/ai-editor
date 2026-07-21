/* Dismiss the boot loader without touching the port-managed 3D tree.
   External (served from 'self') so the CSP needs no script 'unsafe-inline' for it.
   Order of dismissal: explicit scene-ready signal -> window load (+grace)
   -> hard safety timeout (never trap the user behind the loader). */
(function () {
  var loader = document.getElementById('boot-loader');
  if (!loader) return;
  function dismiss() {
    if (loader.dataset.done) return;
    loader.dataset.done = '1';
    /* Narrate the handoff to assistive tech before the loader leaves (it is a
       role=status polite live region) — otherwise the scene-ready transition is silent. */
    var label = loader.querySelector('.boot-label');
    if (label) label.textContent = 'The voyaging mind is ready';
    window.setTimeout(function () { if (loader && loader.parentNode) loader.parentNode.removeChild(loader); }, 700);
  }
  window.addEventListener('gagos:ready', dismiss);           /* PRIMARY: the scene dispatches this on its first rendered frame */
  window.addEventListener('load', function () { window.setTimeout(dismiss, 2500); }); /* grace fallback if the scene never signals */
  window.setTimeout(dismiss, 9000);                          /* hard safety net */
})();
