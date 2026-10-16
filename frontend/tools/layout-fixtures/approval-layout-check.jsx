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
import '../../src/livingMirror/being/FixtureJourneyPage.css';

installFixtureJourney(window);
const root = document.querySelector('.lm-app');
const chrome = document.querySelector('.gagos-chrome');
const result = document.querySelector('.fixture-result');
const guided = new URLSearchParams(location.search).get('mode') !== 'expert';
const compactInset = new URLSearchParams(location.search).has('compact-inset');
// Explicit Conversation owns no selected workspace. Keep its real context
// visible instead of manufacturing active work to obtain the working layout.
const conversation = new URLSearchParams(location.search).has('conversation');
if (conversation) {
  root.dataset.working = 'false';
  root.querySelector('.lm-surface').hidden = true;
  root.querySelector('.lm-workspace-rail').hidden = true;
}
if (compactInset) {
  // Reuse the actual journey scroll frame/minimum, not a duplicate formula.
  const frame = document.createElement('div');
  frame.className = 'fixture-journey__app';
  frame.style.cssText = 'margin-top:165px;height:calc(100dvh - 165px)';
  root.before(frame);
  frame.append(root);
}
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
// Also exercise the first-paint fallback before any observer-fed dock value.
const stopTracking = new URLSearchParams(location.search).has('initial-dock')
  ? () => {} : installWorkspaceDockTracking(root);
// Inert negative controls prove these assertions catch concealment/state
// substitution; none of this code or its query parameters is a product route.
const mutation = new URLSearchParams(location.search).get('control-mutation');
if (mutation === 'body-hidden') root.querySelector('.lm-scene').style.height = '0px';
if (mutation === 'history-hidden') composer.querySelector('.gagos-chat__context').style.display = 'none';
if (mutation === 'fabricated-work') root.dataset.working = 'true';
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
  if (innerWidth <= 767) {
    const body = root.querySelector('.lm-scene').getBoundingClientRect();
    const gap = innerWidth <= 360 || innerHeight <= 739 || root.dataset.workspaceHeight === 'compact' ? 7.5 : -.5;
    if (p.top < body.bottom + gap) failures.push('phone decision hides the being');
    if (body.height < 23.5) failures.push('phone decision leaves no visible body band');
    if (conversation && root.getBoundingClientRect().height >= 740 && body.height < 99.5) failures.push('spare phone room leaves the being thumbnail-sized');
    if (conversation) {
      const context = composer.querySelector('.gagos-chat__context');
      if (root.dataset.working !== 'false') failures.push('Conversation fabricated selected work');
      if (context.clientHeight < 19.5 || getComputedStyle(context).display === 'none') failures.push('Conversation history lost its readable scroll viewport');
      if (root.getBoundingClientRect().height >= 740 && context.clientHeight < 39.5) failures.push('tall Conversation history is squeezed into one line');
      // At a full 568px app height, wrapping Send onto another row must not
      // reduce the organism to the old 24px emergency strip. Check the real
      // CSS/markup, including touch targets, not a copied sizing formula.
      if (innerHeight >= 568 && innerHeight < 740) {
        if (root.getBoundingClientRect().height > innerHeight + .5) failures.push('compact app grows beyond the viewport to claim body room');
        const provisional = new URLSearchParams(location.search).has('initial-dock');
        if (body.height < (provisional ? 55.5 : 79.5)) failures.push('compact Conversation still leaves only a body sliver');
        const input = composer.querySelector('.gagos-input').getBoundingClientRect();
        const send = composer.querySelector('.gagos-send').getBoundingClientRect();
        if (input.height < 43.5 || input.width < 87.5 || send.height < 43.5 || send.width < 43.5) failures.push('compact intake shrinks typing or Send');
        if (Math.abs(input.top - send.top) > .5) failures.push('compact Send still consumes a second intake row');
        const accessories = composer.querySelector('.gagos-bar__accessories');
        const a = accessories.getBoundingClientRect();
        for (const button of accessories.querySelectorAll('button')) {
          const b = button.getBoundingClientRect();
          if (b.height < 43.5 || b.width < 43.5 || getComputedStyle(button).display === 'none') failures.push('compact optional control hidden or below44px');
          if (b.top < a.top + accessories.clientTop - .5 || b.bottom > a.top + accessories.clientTop + accessories.clientHeight + .5) failures.push('scrollbar clips the painted optional control');
        }
        if (accessories.clientWidth > 0 && accessories.scrollWidth > accessories.clientWidth && getComputedStyle(accessories).overflowX !== 'auto') failures.push('compact optional controls cannot scroll');
      }
    }
  }
  if (conversation && innerWidth >= 768) {
    const body = root.querySelector('.lm-scene').getBoundingClientRect();
    if (p.right > body.left + .5 && p.left < body.right - .5
      && p.bottom > body.top + .5 && p.top < body.bottom - .5) failures.push('desktop decision covers the being');
    if (composer.querySelector('.gagos-chat__context').clientHeight < 39.5) failures.push('desktop Conversation history lost its reading space');
  }
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
