// Native-browser CSS regression, not a renderer/backend or hardware test.
// Default supplies the observed 568px phone's 340px composer boundary.
// ?expanded-context uses real composer CSS + the production dock tracker;
// only content/controls are fixture markup, not React or operational proof.
import { installWorkspaceDockTracking } from '../../src/livingMirror/workspaceDock.ts';

const result = document.querySelector('[aria-label="Compact layout regression result"]');
const scene = document.querySelector('.lm-scene');
const surface = document.querySelector('.lm-surface');
const header = document.querySelector('.lm-surface__header');
const body = document.querySelector('.lm-surface__body');
const expandedContext = new URLSearchParams(location.search).has('expanded-context');
const focusLayout = new URLSearchParams(location.search).has('focus');
const receiptReader = focusLayout || new URLSearchParams(location.search).has('receipt');
if (receiptReader) {
  body.replaceChildren(document.querySelector('#fixture-receipt-reader').content.cloneNode(true));
  header.querySelector('h2').textContent = 'fixture/hello.py';
  document.querySelector('.lm-app').dataset.workspaceHeight = 'compact';
  // Test-only negative controls prove both reader edges and receipt coverage
  // are measured; these transforms never enter the product stylesheet.
  const negative = new URLSearchParams(location.search).get('receipt-negative');
  const offsets = { above: -80, below: 96, covered: 32 };
  if (Object.hasOwn(offsets, negative)) body.querySelector('pre').style.transform = `translateY(${offsets[negative]}px)`;
}
const fixedDock = document.querySelector('.fixture-dock');
const pressure = document.querySelector('.fixture-expanded-context');
const dock = expandedContext ? pressure.querySelector('.gagos-chat') : fixedDock;
let focusBaseline = null;
if (focusLayout) {
  const root = document.querySelector('.lm-app');
  root.querySelector('.lm-shell').prepend(document.querySelector('#fixture-focus-header').content.cloneNode(true));
  root.dataset.workspaceHeight = innerHeight === 568 ? 'compact' : 'tall';
  root.style.setProperty('--lm-workspace-app-height', `${innerHeight}px`);
  // Fixed test dock: 138px composer +90px status, with the existing12px gap.
  fixedDock.style.top = `${innerHeight - 228}px`;
  fixedDock.textContent = `CSS-only composer boundary at ${innerHeight - 228}px; nothing is submitted.`;
  focusBaseline = { width: innerWidth, height: innerHeight, scene: scene.getBoundingClientRect(), surface: surface.getBoundingClientRect(), body: body.getBoundingClientRect() };
  root.dataset.beingFocus = 'true';
  // Mutation witness: restore the former unused navigation band. This must
  // fail the gap/body assertions even when reader and controls still fit.
  if (new URLSearchParams(location.search).get('focus-negative') === 'gap') root.style.setProperty('--lm-active-presence-top', '164px');
}
if (expandedContext) {
  fixedDock.hidden = true;
  pressure.hidden = false;
  const stopTracking = installWorkspaceDockTracking(document.querySelector('.lm-app'));
  window.addEventListener('pagehide', stopTracking, { once: true });
}

function checkLayout() {
  const focusHeight = focusLayout && (innerHeight === 568 || innerHeight === 844);
  if ((!focusHeight && innerHeight !== 568) || innerWidth < 320 || innerWidth > 767
    || (focusLayout && (innerWidth !== focusBaseline.width || innerHeight !== focusBaseline.height))) {
    result.dataset.result = 'unavailable';
    result.textContent = `Not checked: use a 320–767 × ${focusLayout ? '568 or 844 viewport; reload Focus cases after resize' : '568 viewport'}. CSS fixture only.`;
    return;
  }
  const bounds = [scene, surface, header, body, dock].map(element => element.getBoundingClientRect());
  const [sceneBox, surfaceBox, headerBox, bodyBox, dockBox] = bounds;
  const failures = [];
  if ((!focusLayout && sceneBox.top < 163.5) || (!expandedContext && sceneBox.height <= 0) || sceneBox.bottom > surfaceBox.top - (focusLayout && innerHeight === 844 ? 0 : 7.5)) failures.push('body/work overlap');
  if (surfaceBox.bottom > dockBox.top - 11.5) failures.push('work/composer overlap');
  // The tall production header intentionally has more padding. Only compact
  // cases own the48px cap; every case still needs a44px reader and controls.
  if (((!focusLayout || innerHeight === 568) && headerBox.height > 48.5) || bodyBox.height < 43.5) failures.push('header consumes readable work');
  if (header.querySelector('h2').getBoundingClientRect().bottom > headerBox.bottom) failures.push('long title escapes header');
  if ([...header.querySelectorAll('button')].some(button => {
    const box = button.getBoundingClientRect();
    return box.width < 43.5 || box.height < 43.5;
  })) failures.push('control smaller than 44px');
  if (expandedContext && [...dock.querySelectorAll('input, button')].some(control => {
    const box = control.getBoundingClientRect();
    return box.width < 43.5 || box.height < 43.5 || box.top < dockBox.top || box.bottom > dockBox.bottom;
  })) failures.push('composer control clipped or smaller than 44px');
  if (receiptReader) {
    const code = body.querySelector('pre');
    const paint = getComputedStyle(code);
    // Measure every painted glyph row, not the first line or trailing blank.
    const range = document.createRange();
    range.selectNodeContents(code);
    const glyphs = [...range.getClientRects()].filter(box => box.width > 0);
    const receipt = body.querySelector('.gagos-receipt').getBoundingClientRect();
    const summary = body.querySelector('.gagos-receipt__reader-summary').getBoundingClientRect();
    if (!glyphs.length || glyphs.some(box => box.top < bodyBox.top - 0.5 || box.bottom > bodyBox.bottom + 0.5 || box.bottom > receipt.top + 0.5 || box.left < bodyBox.left - 0.5 || box.right > bodyBox.left + body.clientWidth + 0.5)) failures.push('complete short code clipped by reader or receipt');
    if (parseFloat(paint.fontSize) < 14) failures.push('code made smaller to fit');
    if (Math.min(summary.bottom, receipt.bottom, bodyBox.bottom) - Math.max(summary.top, receipt.top, bodyBox.top) < 43.5) failures.push('receipt disclosure not fully painted');
    if (document.documentElement.scrollWidth > innerWidth + 0.5) failures.push('page-width overflow');
  }
  if (focusLayout) {
    const controlHeader = document.querySelector('.fixture-focus-header').getBoundingClientRect();
    if (sceneBox.top < controlHeader.bottom + 7.5 || sceneBox.top > controlHeader.bottom + 16.5) failures.push('Focus keeps hidden navigation space');
    if (getComputedStyle(document.querySelector('.lm-navigation')).display !== 'none') failures.push('Focus navigation still painted');
    if (sceneBox.top >= focusBaseline.scene.top - 0.5 || sceneBox.height < focusBaseline.scene.height - 0.5) failures.push('Focus does not reclaim body room');
    if (surfaceBox.top > focusBaseline.surface.top + 0.5 || surfaceBox.bottom < focusBaseline.surface.bottom - 0.5 || bodyBox.height < focusBaseline.body.height - 0.5) failures.push('Focus shrinks retained work');
    if ([...document.querySelectorAll('.fixture-focus-header button')].some(button => {
      const box = button.getBoundingClientRect();
      return box.width < 43.5 || box.height < 43.5 || box.bottom > sceneBox.top;
    })) failures.push('Focus clips critical controls');
  }
  result.dataset.result = failures.length ? 'fail' : 'pass';
  result.textContent = `${failures.length ? `FAIL: ${failures.join('; ')}` : `PASS: body/work/composer separated, work/control ≥44px${receiptReader ? ', complete short code + receipt visible' : ', long title bounded'}${focusLayout ? ', Focus reclaims hidden navigation without shrinking work' : ''}`}. CSS only; no organism/backend/device proof.`;
}

checkLayout();
window.addEventListener('resize', checkLayout);
const observer = new ResizeObserver(checkLayout);
for (const element of [scene, surface, header, body]) observer.observe(element);
observer.observe(dock);
if (receiptReader) {
  observer.observe(body.querySelector('.lm-artifact'));
  observer.observe(body.querySelector('.gagos-receipt'));
  document.fonts.ready.then(checkLayout);
}
window.addEventListener('pagehide', () => observer.disconnect(), { once: true });
