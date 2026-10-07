// Actual panel markup + production CSS in the native browser. SSR leaves all
// decision buttons inert; the existing fixture transport fences imports too.
// This is layout evidence, never permission/backend/handset/AT acceptance.
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import '@fontsource-variable/inter';
import '@fontsource-variable/jetbrains-mono';
import { installFixtureJourney } from '../../src/livingMirror/being/installFixtureJourney';
import GuidedApprovalPanel from '../../src/livingMirror/GuidedApprovalPanel';
import ApprovalPanel from '../../src/superbrain/components/ui/ApprovalPanel';
import { installWorkspaceDockTracking } from '../../src/livingMirror/workspaceDock';

installFixtureJourney(window);
const root = document.querySelector('.lm-app');
const chrome = document.querySelector('.gagos-chrome');
const result = document.querySelector('.fixture-result');
const guided = new URLSearchParams(location.search).get('mode') !== 'expert';
root.dataset.experienceMode = guided ? 'beginner' : 'expert';
root.querySelector('.lm-shell').dataset.experienceMode = root.dataset.experienceMode;
chrome.dataset.approvalPending = 'true';
chrome.insertAdjacentHTML('beforeend', renderToStaticMarkup(createElement(guided ? GuidedApprovalPanel : ApprovalPanel, {
  pending: { token: 'inert-layout-example', prompt: '', summary: 'CSS fixture: inspect the whole proposed change.',
    explanation: 'Long approval explanation, not a live action. '.repeat(12),
    diff: '--- /dev/null\n+++ fixture/example.txt\n' + '+Readable proposal line\n'.repeat(80) + '+End of proposed change',
    kind: 'create', filepath: 'fixture/example.txt', content: '', command: '', url: '' },
  onSettled: () => {},
})));
const panel = chrome.querySelector('.approval-panel');
const reading = panel.querySelector('.approval-body');
const details = panel.querySelector('details');
const actions = [...panel.querySelectorAll('.approval-actions button')];
const footer = panel.querySelector('.approval-actions');
const composer = chrome.querySelector('.gagos-chat');
const header = root.querySelector('.lm-header');
const stopTracking = installWorkspaceDockTracking(root);
let frame = null;
let disposed = false;
function scheduleCheck() {
  if (frame !== null || disposed) return;
  frame = requestAnimationFrame(() => { frame = null; if (!disposed) checkLayout(); });
}
function checkLayout() {
  const failures = [];
  const p = panel.getBoundingClientRect();
  const f = footer.getBoundingClientRect();
  // Unrelated readable work must not bleed through a critical decision. An
  // opaque backing is independent of the retained reader and the 3D scene;
  // blur alone can still turn their text into competing ghost lettering.
  const paint = getComputedStyle(panel);
  const color = paint.backgroundColor.match(/^rgba?\(([^)]+)\)$/)?.[1].split(',').map(Number);
  if (!color || (color[3] ?? 1) < 1) failures.push('unrelated work can show through the decision');
  if (paint.animationName !== 'none' && paint.animationDuration.split(',').some(duration => parseFloat(duration) > 0)) failures.push('critical decision travels into position');
  if (!reading || getComputedStyle(reading).overflowY !== 'auto' || reading.clientHeight < 43) failures.push('proposal has no usable scroll viewport');
  if (panel.scrollHeight > panel.clientHeight + 1) failures.push('dialog root clips its content');
  for (const button of actions) {
    const b = button.getBoundingClientRect();
    if (b.height < 43.5 || b.width < 43.5 || b.top < p.top || b.bottom > p.bottom + .5) failures.push('decision action clipped or below44px');
  }
  if (p.top < header.getBoundingClientRect().bottom + 7.5) failures.push('dialog covers Stop');
  if (p.bottom > composer.getBoundingClientRect().top - 11.5) failures.push('dialog covers intake');
  if (innerWidth >= 361 && innerWidth <= 767 && innerHeight >= 740
    && p.top < root.querySelector('.lm-scene').getBoundingClientRect().bottom - .5) failures.push('tall-phone decision hides the being');
  if (reading && (reading.getBoundingClientRect().bottom > f.top + .5 || reading.contains(footer))) failures.push('actions scroll with the proposal');
  result.dataset.result = failures.length ? 'fail' : 'pass';
  result.textContent = `${failures.length ? 'FAIL: ' + failures.join('; ') : 'PASS: opaque decision, scrollable proposal, visible44px decisions, clear Stop/intake'}. Inert actual markup/CSS only.`;
}
details?.addEventListener('toggle', scheduleCheck);
panel.addEventListener('animationend', scheduleCheck);
composer.addEventListener('animationend', scheduleCheck);
composer.addEventListener('animationcancel', scheduleCheck);
window.addEventListener('resize', scheduleCheck);
const observer = new ResizeObserver(scheduleCheck);
for (const e of [panel, footer, composer, header, ...(reading ? [reading] : [])]) observer.observe(e);
document.fonts.ready.then(scheduleCheck);
scheduleCheck();
window.addEventListener('pagehide', () => {
  disposed = true; if (frame !== null) cancelAnimationFrame(frame);
  stopTracking();
  observer.disconnect(); window.removeEventListener('resize', scheduleCheck);
  details?.removeEventListener('toggle', scheduleCheck);
  panel.removeEventListener('animationend', scheduleCheck);
  composer.removeEventListener('animationend', scheduleCheck);
  composer.removeEventListener('animationcancel', scheduleCheck);
}, { once: true });
