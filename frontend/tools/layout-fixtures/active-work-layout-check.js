// Actual browser layout assertions against production CSS; not a DOM-emulated
// visual test, a live receipt or an operator/hardware acceptance claim.
import { installWorkspaceDockTracking } from '../../src/livingMirror/workspaceDock.ts';

const root = document.querySelector('.lm-app');
const scene = root.querySelector('.lm-scene');
const work = root.querySelector('.lm-surface');
const composer = root.querySelector('.gagos-chat');
const input = composer.querySelector('input');
const notice = root.querySelector('.lm-connection');
const rail = root.querySelector('.lm-workspace-rail');
const status = root.querySelector('.gagos-status');
const result = document.querySelector('.fixture-result');
const guided = new URLSearchParams(location.search).get('mode') === 'guided';
if (guided) {
  root.dataset.experienceMode = 'beginner';
  root.querySelector('.lm-shell').dataset.experienceMode = 'beginner';
}
// Reproduce the journey's reserved driver band without its transport or GPU.
// This is an available-app-height CSS regression, not a handset simulation.
const inset = new URLSearchParams(location.search).has('inset');
// An unconstrained tall phone must not leave the being thumbnail-sized while
// its reader consumes all spare height. Exercise real CSS, not its formula.
const presenceRoom = new URLSearchParams(location.search).has('presence-room');
if (inset) {
  root.style.marginTop = '165px';
  root.style.height = 'calc(100dvh - 165px)';
  root.style.minHeight = '0';
}
// CSS-state-only extreme viewport regression; this does NOT emulate an IME
// or claim that a 140px viewport can hold the whole application/control stack.
const smallKeyboard = new URLSearchParams(location.search).has('keyboard-small');
const focus = new URLSearchParams(location.search).has('focus');
if (focus) root.dataset.beingFocus = 'true';
const restingFocus = focus && new URLSearchParams(location.search).has('resting');
if (restingFocus) { root.dataset.working = 'false'; work.hidden = true; }
if (smallKeyboard) {
  root.dataset.keyboardOpen = 'true';
  root.style.setProperty('--lm-visible-viewport-height', '140px');
}
const stopTracking = installWorkspaceDockTracking(root);
let checkFrame = null;
let disposed = false;
function scheduleCheck() {
  if (checkFrame !== null || disposed) return;
  checkFrame = requestAnimationFrame(() => {
    checkFrame = null;
    if (!disposed) checkLayout();
  });
}
const details = notice.querySelector('details');
details.addEventListener('toggle', () => {
  notice.dataset.detailsOpen = String(details.open);
  scheduleCheck();
});

function overlaps(a, b) {
  return a.width > 0 && a.height > 0 && b.width > 0 && b.height > 0
    && a.left < b.right - .5 && a.right > b.left + .5
    && a.top < b.bottom - .5 && a.bottom > b.top + .5;
}

function checkLayout() {
  if (presenceRoom && !(innerWidth >= 361 && innerWidth <= 767 && innerHeight >= 740)) {
    result.dataset.result = 'unavailable';
    result.textContent = 'Presence-room regression requires a tall phone viewport ≥361px wide and ≥740px high. CSS only.';
    return;
  }
  if (inset && !(innerWidth >= 361 && innerWidth <= 767 && innerHeight >= 740)) {
    result.dataset.result = 'unavailable';
    result.textContent = 'Inset reading regression requires a tall phone viewport ≥361px wide and ≥740px high. CSS only.';
    return;
  }
  if (smallKeyboard) root.style.setProperty('--lm-keyboard-inset', `${Math.max(0, innerHeight - 140)}px`);
  const phone = innerWidth <= 767;
  const desktop = innerWidth >= 768 && innerHeight >= 521;
  if (!phone && !desktop) {
    result.dataset.result = 'unavailable';
    result.textContent = 'Not checked: use a phone or work-side dock ≥768×521. CSS fixture only.';
    return;
  }
  const [bodyBox, workBox, composerBox, noticeBox] = [scene, work, composer, notice].map(el => el.getBoundingClientRect());
  const failures = [];
  if (presenceRoom) {
    if (bodyBox.height < 239.5) failures.push('spare tall-phone height leaves organism thumbnail-sized');
    if (workBox.height < 191.5) failures.push('larger phone presence starves retained reader');
  }
  if (restingFocus) {
    if (!desktop) {
      result.dataset.result = 'unavailable';
      result.textContent = 'Resting Focus regression checks Expert tablet/desktop ≥768×521 only. CSS fixture, not organism proof.';
      return;
    }
    const headerBand = innerWidth >= 1200 ? 144 : 0;
    if (Math.abs(bodyBox.top - headerBand) > .5 || Math.abs(bodyBox.height - (innerHeight - headerBand)) > .5
      || Math.abs(bodyBox.left) > .5 || Math.abs(bodyBox.width - innerWidth) > .5) failures.push('resting Expert Focus pane changed');
    result.dataset.result = failures.length ? 'fail' : 'pass';
    result.textContent = `${failures.length ? `FAIL: ${failures.join('; ')}` : `PASS: resting Expert Focus preserves ${headerBand}px header band`}. CSS fixture only; no organism/backend/device proof.`;
    return;
  }
  if (smallKeyboard) {
    if (!phone) {
      result.dataset.result = 'unavailable';
      result.textContent = 'Use a phone viewport for the simulated keyboard notice-cap check. CSS only.';
      return;
    }
    // getComputedStyle preserves calc() for unregistered custom properties;
    // use the authored extreme's literal expected result, not a copied helper.
    if (noticeBox.height > 56.5 || noticeBox.top < composerBox.bottom + 7.5) failures.push('keyboard notice cap overridden');
    result.dataset.result = failures.length ? 'fail' : 'pass';
    result.textContent = `${failures.length ? `FAIL: ${failures.join('; ')}` : 'PASS: 140px CSS viewport notice cap ≤56px; no intake overlap'}. Notice CSS only; no keyboard/IME/full-layout/device proof.`;
    return;
  }
  const contentBox = work.querySelector('.lm-surface__content').getBoundingClientRect();
  const body = work.querySelector('.lm-surface__body');
  const workBodyBox = body.getBoundingClientRect();
  if (inset && workBodyBox.height < 119.5) failures.push('inset app starves retained reader');
  const bodyStyle = getComputedStyle(body);
  const readableHeight = Math.min(contentBox.height, workBodyBox.height) - parseFloat(bodyStyle.paddingTop) - parseFloat(bodyStyle.paddingBottom);
  if (contentBox.height < 43.5 || readableHeight < 19.5) failures.push('work content has no readable line');
  if (work !== root.querySelector('.lm-surface') || input !== root.querySelector('.gagos-input')) failures.push('persistent node replaced');
  if (workBox.height < 93.5 || workBox.bottom > composerBox.top - 11.5) failures.push('work unreadable or touches composer');
  if (noticeBox.top < composerBox.bottom + 7.5 || overlaps(workBox, noticeBox)) failures.push('diagnostics escape reserved band');
  if (desktop) {
    if (Math.abs(bodyBox.width - innerWidth * .32) > .5) failures.push('active body pane lost 32/68 split');
    if ([work, composer, notice, rail, status].some(el => overlaps(bodyBox, el.getBoundingClientRect()))) failures.push('control covers body pane');
    if (workBox.top < rail.getBoundingClientRect().bottom + 7.5) failures.push('switcher covers work');
    if (innerHeight > 650 && workBox.height < 159.5) failures.push('desktop work too short');
  } else {
    const headerBox = root.querySelector('.lm-header').getBoundingClientRect();
    // Guided has no navigation row. Its 44px Stop row ends at106px;
    // do not reserve the hidden Expert row's58px here. Test actual CSS,
    // not a copied presence-height formula or a hand-set body rectangle.
    if (guided && (bodyBox.top < headerBox.bottom + 11.5 || bodyBox.top > headerBox.bottom + 12.5)) failures.push('Guided presence wastes hidden navigation band or covers Stop');
    if ([work, composer, notice].some(el => overlaps(bodyBox, el.getBoundingClientRect()))) failures.push('work/control covers phone body pane');
    if (noticeBox.height > 82.5) failures.push('phone diagnostics taller than reserved band');
    const recoveryBox = notice.querySelector('.lm-connection__actions button').getBoundingClientRect();
    if (recoveryBox.height < 43.5 || recoveryBox.top < noticeBox.top - .5 || recoveryBox.bottom > noticeBox.bottom + .5) failures.push('phone recovery control clipped');
  }
  if ([...composer.querySelectorAll('input, button')].some(el => {
    const box = el.getBoundingClientRect();
    return box.height < 43.5 || box.width < 43.5 || box.top < composerBox.top - .5 || box.bottom > composerBox.bottom + .5
      || box.left < composerBox.left - .5 || box.right > composerBox.right + .5;
  })) failures.push('intake control clipped or smaller than 44px');
  result.dataset.result = failures.length ? 'fail' : 'pass';
  result.textContent = `${failures.length ? `FAIL: ${failures.join('; ')}` : 'PASS: clear body, retained work/input, bounded diagnostics'}${focus ? ' (active Focus)' : ''}. CSS fixture only; no organism/backend/device proof.`;
}

scheduleCheck();
window.addEventListener('resize', scheduleCheck);
notice.addEventListener('scroll', scheduleCheck);
// Entrance transforms do not resize the bar. Retain any initial failure,
// but refresh the settled layout instead of caching that moving rectangle.
composer.addEventListener('animationend', scheduleCheck);
composer.addEventListener('animationcancel', scheduleCheck);
const observer = new ResizeObserver(scheduleCheck);
for (const element of [scene, work, composer, notice, rail, status,
  work.querySelector('.lm-surface__header'), work.querySelector('.lm-surface__content'), work.querySelector('.lm-surface__body'),
  composer.querySelector('.gagos-bar'), ...composer.querySelectorAll('input, button')]) observer.observe(element);
// The real self-hosted font baseline can finish after the initial geometry.
// Recheck cached fixture results then; don't accept a fallback-font snapshot.
document.fonts.ready.then(scheduleCheck);
window.addEventListener('pagehide', () => {
  disposed = true;
  if (checkFrame !== null) cancelAnimationFrame(checkFrame);
  stopTracking();
  observer.disconnect();
  window.removeEventListener('resize', scheduleCheck);
  notice.removeEventListener('scroll', scheduleCheck);
  composer.removeEventListener('animationend', scheduleCheck);
  composer.removeEventListener('animationcancel', scheduleCheck);
}, { once: true });
