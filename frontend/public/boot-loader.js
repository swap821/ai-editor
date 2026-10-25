/* Dismiss the boot loader without touching the port-managed 3D tree.
   External (served from 'self') so the CSP needs no script 'unsafe-inline' for it.
   Order of dismissal: real controls/scene-ready signal -> window load (+grace)
   -> hard safety timeout (never trap the user behind the loader). */
(function () {
  var loader = document.getElementById('boot-loader');
  if (!loader || loader.dataset.done) return;
  var graceTimer = 0;
  var safetyTimer = 0;
  function dismiss(message) {
    if (loader.dataset.done) return;
    loader.dataset.done = '1';
    window.removeEventListener('gagos:controls-ready', controlsReady);
    window.removeEventListener('gagos:ready', sceneReady);
    window.removeEventListener('load', loaded);
    window.clearTimeout(graceTimer);
    window.clearTimeout(safetyTimer);
    /* Narrate the handoff to assistive tech before the loader leaves (it is a
       role=status polite live region) — otherwise the scene-ready transition is silent. */
    var label = loader.querySelector('.boot-label');
    if (label) label.textContent = message;
    window.setTimeout(function () { if (loader && loader.parentNode) loader.parentNode.removeChild(loader); }, 700);
  }
  function controlsReady() { dismiss('Controls ready.'); }
  function sceneReady() { dismiss('The voyaging mind is ready'); }
  function timedDismiss() { dismiss('Opening GAGOS.'); } /* A timeout proves no readiness. */
  function loaded() { graceTimer = window.setTimeout(timedDismiss, 2500); }
  window.addEventListener('gagos:controls-ready', controlsReady);
  window.addEventListener('gagos:ready', sceneReady); /* Actual first rendered frame, not a guessed timer. */
  window.addEventListener('load', loaded);
  safetyTimer = window.setTimeout(timedDismiss, 9000);
  if (document.querySelector('.lm-app[data-controls-ready="true"]')) controlsReady();
})();
