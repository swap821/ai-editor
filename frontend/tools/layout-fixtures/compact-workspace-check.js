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
const fixedDock = document.querySelector('.fixture-dock');
const pressure = document.querySelector('.fixture-expanded-context');
const dock = expandedContext ? pressure.querySelector('.gagos-chat') : fixedDock;
if (expandedContext) {
  fixedDock.hidden = true;
  pressure.hidden = false;
  const stopTracking = installWorkspaceDockTracking(document.querySelector('.lm-app'));
  window.addEventListener('pagehide', stopTracking, { once: true });
}

function checkLayout() {
  if (innerHeight !== 568 || innerWidth < 320 || innerWidth > 767) {
    result.dataset.result = 'unavailable';
    result.textContent = 'Not checked: use a 320–767 × 568 viewport. CSS fixture only.';
    return;
  }
  const bounds = [scene, surface, header, body, dock].map(element => element.getBoundingClientRect());
  const [sceneBox, surfaceBox, headerBox, bodyBox, dockBox] = bounds;
  const failures = [];
  if (sceneBox.top < 163.5 || (!expandedContext && sceneBox.height <= 0) || sceneBox.bottom > surfaceBox.top - 7.5) failures.push('body/work overlap');
  if (surfaceBox.bottom > dockBox.top - 11.5) failures.push('work/composer overlap');
  if (headerBox.height > 48.5 || bodyBox.height < 43.5) failures.push('header consumes readable work');
  if (header.querySelector('h2').getBoundingClientRect().bottom > headerBox.bottom) failures.push('long title escapes header');
  if ([...header.querySelectorAll('button')].some(button => {
    const box = button.getBoundingClientRect();
    return box.width < 43.5 || box.height < 43.5;
  })) failures.push('control smaller than 44px');
  if (expandedContext && [...dock.querySelectorAll('input, button')].some(control => {
    const box = control.getBoundingClientRect();
    return box.width < 43.5 || box.height < 43.5 || box.top < dockBox.top || box.bottom > dockBox.bottom;
  })) failures.push('composer control clipped or smaller than 44px');
  result.dataset.result = failures.length ? 'fail' : 'pass';
  result.textContent = `${failures.length ? `FAIL: ${failures.join('; ')}` : 'PASS: body/work/composer separated, long title bounded, work/control ≥44px'}. CSS only; no organism/backend/device proof.`;
}

checkLayout();
window.addEventListener('resize', checkLayout);
const observer = new ResizeObserver(checkLayout);
for (const element of [scene, surface, header, body]) observer.observe(element);
observer.observe(dock);
window.addEventListener('pagehide', () => observer.disconnect(), { once: true });
