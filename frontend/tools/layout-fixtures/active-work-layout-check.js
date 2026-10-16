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
// Diagnostic text must not itself intercept the controls it measures.
result.style.pointerEvents = 'none';
const navigation = root.querySelector('.lm-navigation');
const accessories = composer.querySelector('.gagos-bar__accessories');
const context = composer.querySelector('.gagos-chat__context');
// Opt-in inert stress controls exercise the real accessories scroll owner.
// These are not product actions or a voice/model capability claim.
if (new URLSearchParams(location.search).has('accessory-overflow')) {
  for (const label of ['Local (Ollama)', 'Swarm off']) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'gagos-btn';
    button.textContent = label;
    accessories.append(button);
  }
}
const guided = new URLSearchParams(location.search).get('mode') === 'guided';
const initialControls = new URLSearchParams(location.search).has('initial-controls');
const initialIntake = new URLSearchParams(location.search).has('intake-first-paint');
// Actual product dock state: its legacy minimized scale must not shrink the
// short active branch's44px controls. This is CSS state, not task activity.
if (new URLSearchParams(location.search).has('minimized')) composer.querySelector('.gagos-bar').classList.add('is-minimized');
if (guided) {
  root.dataset.experienceMode = 'beginner';
  root.querySelector('.lm-shell').dataset.experienceMode = 'beginner';
}
// Reproduce the journey's reserved driver band without its transport or GPU.
// This is an available-app-height CSS regression, not a handset simulation.
const compactInset = new URLSearchParams(location.search).has('compact-inset');
const inset = new URLSearchParams(location.search).has('inset') || compactInset;
// Reproduce a tall browser containing a short app. Do not force its private
// geometry classification or pane coordinates: the real tracker/CSS own them.
const availableHeight = new URLSearchParams(location.search).has('available-height');
// A compact app with spare room must support several readable lines, not
// freeze at its emergency44px floor. The being still owns a100px clear band.
const readerRoom = new URLSearchParams(location.search).has('reader-room');
// An unconstrained tall phone must not leave the being thumbnail-sized while
// its reader consumes all spare height. Exercise real CSS, not its formula.
const presenceRoom = new URLSearchParams(location.search).has('presence-room');
const shortLandscape = new URLSearchParams(location.search).has('short-landscape');
if (inset) {
  root.style.marginTop = '165px';
  root.style.height = 'calc(100dvh - 165px)';
  // The compact product keeps a520px minimum. Its development viewport may
  // scroll; do not disable that real contract and demand an impossible stack.
  root.style.minHeight = compactInset ? '520px' : '0';
  // Match the real journey's app-relative fixed controls too. Otherwise a
  // switch fixed to the browser can falsely clear the inset Stop trigger.
  if (compactInset || availableHeight) root.style.contain = 'layout';
}
// CSS-state-only extreme viewport regression; this does NOT emulate an IME
// or claim that a 140px viewport can hold the whole application/control stack.
const smallKeyboard = new URLSearchParams(location.search).has('keyboard-small');
const focus = new URLSearchParams(location.search).has('focus');
if (focus) root.dataset.beingFocus = 'true';
const restingFocus = focus && new URLSearchParams(location.search).has('resting');
if (restingFocus) { root.dataset.working = 'false'; work.hidden = true; }
// First contact owns no selected work. Exercise the same production CSS and
// actual hit testing, without admitting a task or invoking any product action.
const restingContact = new URLSearchParams(location.search).has('resting-contact');
const phoneRest = new URLSearchParams(location.search).has('phone-rest');
const contextOverflow = new URLSearchParams(location.search).has('context-overflow');
if (restingContact || phoneRest) {
  root.dataset.working = 'false';
  work.hidden = true;
  rail.hidden = true;
  rail.style.display = 'none';
  const account = document.createElement('button');
  account.type = 'button';
  account.className = 'gagos-pill gagos-pill--bond';
  account.textContent = 'Account not linked';
  status.append(account);
  if (contextOverflow) {
    // Test-only long history, not product copy or a keyboard-access claim.
    // Native End/scroll must reach its final line before this stress can PASS.
    context.tabIndex = 0;
    for (let line = 1; line <= 24; line++) {
      const paragraph = document.createElement('p');
      paragraph.textContent = `Inert fixture history line ${line}; no task or receipt.`;
      context.append(paragraph);
    }
  }
}
if (phoneRest) {
  // Match the real shell's responsive two-control branch, not the desktop
  // launchers in the inert HTML. This fixture has no backend/action owner.
  const conversation = navigation.firstElementChild;
  const menu = document.createElement('details');
  menu.className = 'lm-expert-mobile-surfaces';
  const summary = document.createElement('summary');
  summary.textContent = 'Workspaces';
  menu.append(summary);
  navigation.replaceChildren(conversation, menu);
  const hint = document.createElement('div');
  hint.className = 'gagos-hint';
  hint.setAttribute('role', 'note');
  hint.setAttribute('aria-label', 'Fixture optional onboarding hint');
  const copy = document.createElement('span');
  copy.className = 'gagos-hint__text';
  copy.textContent = 'ORGANS · forge shortcut — fixture only';
  const dismiss = document.createElement('button');
  dismiss.className = 'gagos-hint__dismiss';
  dismiss.textContent = '×';
  dismiss.type = 'button';
  hint.append(copy, dismiss);
  composer.append(hint);
}
// Explicit negative controls for the CSS-only assertion helper. These cannot
// affect the product route and carry no transport, organism or task state.
const controlMutation = new URLSearchParams(location.search).get('control-mutation');
if (controlMutation === 'body-boundary') scene.style.top = '160px';
if (controlMutation === 'header-overlap') root.querySelector('.lm-brand').style.width = '120px';
if (controlMutation === 'accessory-clip') accessories.style.height = '44px';
if (controlMutation === 'send-covered') navigation.style.top = 'calc(100% - 180px)';
if (controlMutation === 'context-clip') context.style.overflowY = 'hidden';
if (controlMutation === 'rest-presence-waste') scene.style.bottom = '45%';
if (controlMutation === 'rest-context-starved') context.style.maxHeight = '0px';
if (controlMutation === 'reader-starved') root.style.setProperty('--lm-compact-work-budget', '102px');
if (controlMutation === 'reader-body-hidden') scene.style.height = '0px';
if (controlMutation === 'intake-invisible' || controlMutation === 'intake-shifted') {
  const bar = composer.querySelector('.gagos-bar');
  // A deterministic faulty paint, not a transition away from the good one.
  bar.style.transition = 'none';
  if (controlMutation === 'intake-invisible') bar.style.opacity = '0';
  else bar.style.transform = 'translateY(12px)';
}
if (controlMutation === 'mode-wrapper-hit') root.querySelector('.gagos-experience-switch').style.pointerEvents = 'auto';
if (controlMutation === 'send-edge-covered') {
  const edge = document.createElement('span');
  Object.assign(edge.style, { position: 'absolute', right: '9px', top: '0', bottom: '0', width: '5px', zIndex: '100', pointerEvents: 'auto' });
  composer.querySelector('.gagos-bar').append(edge);
}
if (smallKeyboard) {
  root.dataset.keyboardOpen = 'true';
  root.style.setProperty('--lm-visible-viewport-height', '140px');
}
if (initialIntake) {
  // Control the actual CSS animation clock on the inert intake only. A late
  // settled screenshot cannot establish that its initial paint is usable.
  for (const animation of composer.querySelector('.gagos-bar').getAnimations()) {
    if (!('animationName' in animation)) continue;
    animation.pause();
    animation.currentTime = 0;
  }
}
const stopTracking = initialControls ? () => {} : installWorkspaceDockTracking(root);
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

function checkDesktopControls(failures, shortLandscape = false) {
  const switchBox = root.querySelector('.gagos-experience-switch').getBoundingClientRect();
  for (const element of root.querySelectorAll('.lm-brand, .lm-stop, .lm-navigation')) {
    if (overlaps(switchBox, element.getBoundingClientRect())) failures.push('mode controls cover header or navigation');
  }
  if (switchBox.left < -.5 || switchBox.right > innerWidth + .5) failures.push('mode controls escape viewport');
  if ([...root.querySelectorAll('.gagos-experience-switch button, .lm-stop > button')].some(button => {
    const box = button.getBoundingClientRect();
    return box.width < 43.5 || box.height < 43.5;
  })) failures.push('mode or Stop target smaller than44px');
  const railBox = rail.getBoundingClientRect();
  if (railBox.width > 0 && railBox.height > 0 && switchBox.bottom > railBox.top - 7.5) failures.push('mode controls cover retained switcher');
  // Horizontal off-screen items may be scrolled into view. On tablets AND
  // wide desktops,44px painted targets must retain native scrollbar room.
  const navBox = navigation.getBoundingClientRect();
  const visibleTop = navBox.top + navigation.clientTop;
  const visibleBottom = visibleTop + navigation.clientHeight;
  if (navBox.height > 0 && [...navigation.querySelectorAll('button, summary')].some(element => {
    // Chromium can expose a cached layout rectangle for closed details
    // content. Only its own summary remains a painted/reachable target.
    const closedDetails = element.closest('details:not([open])');
    if (closedDetails && element !== closedDetails.querySelector(':scope > summary')) return false;
    const box = element.getBoundingClientRect();
    return box.width > 0 && box.height > 0 && (box.height < 43.5 || box.top < visibleTop - .5 || box.bottom > visibleBottom + .5);
  })) failures.push('navigation targets clipped vertically');
  if (navBox.height > 0 && [...root.querySelectorAll('.lm-brand, .lm-stop')].some(element => overlaps(navBox, element.getBoundingClientRect()))) {
    failures.push('navigation covers header or Stop');
  }
  if (innerWidth >= 1200 && navBox.height > 0 && !shortLandscape) {
    const bodyTop = scene.getBoundingClientRect().top;
    if (Math.abs(bodyTop - root.getBoundingClientRect().top - 144) > .5) failures.push('wide body boundary moved');
    if (navBox.bottom > bodyTop + .5) failures.push('wide navigation covers the body band');
  }
}

function checkLayout() {
  if (phoneRest) {
    checkPhoneRest();
    return;
  }
  if (initialIntake) {
    checkInitialIntake();
    return;
  }
  if (restingContact) {
    checkRestingContact();
    return;
  }
  if (presenceRoom && !(innerWidth >= 361 && innerWidth <= 767 && innerHeight >= 740)) {
    result.dataset.result = 'unavailable';
    result.textContent = 'Presence-room regression requires a tall phone viewport ≥361px wide and ≥740px high. CSS only.';
    return;
  }
  if (compactInset && !(innerWidth >= 320 && innerWidth <= 767 && innerHeight <= 739)) {
    result.dataset.result = 'unavailable';
    result.textContent = 'Compact inset regression requires a short phone viewport. CSS only.';
    return;
  }
  if (inset && !compactInset && !(innerWidth >= 361 && innerWidth <= 767 && innerHeight >= 740)) {
    result.dataset.result = 'unavailable';
    result.textContent = 'Inset reading regression requires a tall phone viewport ≥361px wide and ≥740px high. CSS only.';
    return;
  }
  if (smallKeyboard) root.style.setProperty('--lm-keyboard-inset', `${Math.max(0, innerHeight - 140)}px`);
  const phone = innerWidth <= 767;
  const desktop = innerWidth >= 768 && (innerHeight >= 521 || shortLandscape);
  if (shortLandscape && !(innerWidth >= 768 && innerHeight >= 360 && innerHeight <= 520)) {
    result.dataset.result = 'unavailable';
    result.textContent = 'Short-landscape regression requires ≥768px width and360..520px height. CSS only.';
    return;
  }
  if (!phone && !desktop) {
    result.dataset.result = 'unavailable';
    result.textContent = 'Not checked: use a phone or work-side dock ≥768×521. CSS fixture only.';
    return;
  }
  const [bodyBox, workBox, composerBox, noticeBox] = [scene, work, composer, notice].map(el => el.getBoundingClientRect());
  const failures = [];
  if (desktop) checkDesktopControls(failures, shortLandscape);
  if (shortLandscape) {
    const appBox = root.getBoundingClientRect();
    const headerBox = root.querySelector('.lm-header').getBoundingClientRect();
    const modeBox = root.querySelector('.gagos-experience-switch').getBoundingClientRect();
    if (appBox.height > innerHeight + .5) failures.push('short app forces offscreen controls');
    if (bodyBox.top < headerBox.bottom + 11.5 || bodyBox.height < innerHeight * .6) failures.push('short body not clear/readable below Stop');
    if ([work, composer, notice, rail, status, navigation].some(element => overlaps(bodyBox, element.getBoundingClientRect()))) failures.push('short controls cover anatomy');
    if (overlaps(modeBox, root.querySelector('.lm-stop').getBoundingClientRect())) failures.push('short modes cover Stop');
    for (const element of root.querySelectorAll('.lm-stop > button, .gagos-experience-switch button')) {
      const box = element.getBoundingClientRect();
      if (box.width < 43.5 || box.height < 43.5) failures.push('short mode/Stop target below44px');
    }
    if (workBox.top < navigation.getBoundingClientRect().bottom - .5 && !focus && !guided) failures.push('short navigation covers reader');
    if (composerBox.bottom > appBox.bottom + .5 || noticeBox.bottom > appBox.bottom + .5) failures.push('short dock escapes app');
    if (guided && rail.getBoundingClientRect().height > 0) failures.push('Guided exposes obscured switcher');
  }
  if (initialControls) {
    result.dataset.result = desktop ? (failures.length ? 'fail' : 'pass') : 'unavailable';
    result.textContent = `${desktop ? (failures.length ? `FAIL: ${failures.join('; ')}` : 'PASS: header/Stop/mode/navigation clear before control measurements') : 'Use desktop/tablet viewport'}. First-paint control CSS only; dock/reader/organism/backend/device not checked.`;
    return;
  }
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
  if (availableHeight) {
    const appBox = root.getBoundingClientRect();
    if (!(inset && innerHeight >= 740 && appBox.height < 740)) failures.push('fixture does not exercise tall-browser short-app mismatch');
    if (work.querySelector('.lm-surface__header').getBoundingClientRect().height > 48.5) failures.push('short available app retains tall reading header');
    if (workBodyBox.height < 43.5 || bodyBox.height < (guided ? 99.5 : 53.5)) failures.push('short available app starves reading or being');
  }
  if (inset && !compactInset && root.getBoundingClientRect().height >= 740 && workBodyBox.height < 119.5) failures.push('tall available app starves retained reader');
  if (compactInset && (workBodyBox.height < 43.5 || bodyBox.bottom > workBox.top + .5)) failures.push('compact inset app starves reader or overlaps body');
  const bodyStyle = getComputedStyle(body);
  const readableHeight = Math.min(contentBox.height, workBodyBox.height) - parseFloat(bodyStyle.paddingTop) - parseFloat(bodyStyle.paddingBottom);
  if (readerRoom) {
    const appBox = root.getBoundingClientRect();
    // Qualify the observed spare-space case, not impossible tiny stacks or
    // a fixed copy of the production allocation formula.
    const freeBand = composerBox.top - 12 - bodyBox.top;
    if (!phone || root.dataset.workspaceHeight !== 'compact' || freeBand < 227.5 || appBox.height >= 740) {
      failures.push('reader-room fixture does not exercise compact spare space');
    }
    if (readableHeight < 61.5) failures.push('spare compact space leaves reader at emergency one-line floor');
    if (bodyBox.height < 99.5) failures.push('reader growth hides the compact being');
  }
  if (contentBox.height < 43.5 || readableHeight < 19.5) failures.push('work content has no readable line');
  if (work !== root.querySelector('.lm-surface') || input !== root.querySelector('.gagos-input')) failures.push('persistent node replaced');
  if (workBox.height < 93.5 || workBox.bottom > composerBox.top - 11.5) failures.push('work unreadable or touches composer');
  if (noticeBox.top < composerBox.bottom + 7.5 || overlaps(workBox, noticeBox)) failures.push('diagnostics escape reserved band');
  if (desktop) {
    if (Math.abs(bodyBox.width - innerWidth * .32) > .5) failures.push('active body pane lost 32/68 split');
    if ([work, composer, notice, rail, status].some(el => overlaps(bodyBox, el.getBoundingClientRect()))) failures.push('control covers body pane');
    if (rail.getBoundingClientRect().height > 0 && workBox.top < rail.getBoundingClientRect().bottom + 7.5) failures.push('switcher covers work');
    if (innerHeight > 650 && workBox.height < 159.5) failures.push('desktop work too short');
  } else {
    for (const element of root.querySelectorAll('.lm-stop > button, .gagos-experience-switch button')) {
      const box = element.getBoundingClientRect();
      const x = box.left + box.width / 2, y = box.top + box.height / 2;
      if ([[x, y], [box.left + 2, y], [box.right - 2, y], [x, box.top + 2], [x, box.bottom - 2]].some(([px, py]) => {
        const hit = document.elementFromPoint(px, py);
        return !hit || !element.contains(hit);
      })) failures.push('phone mode/Stop hit intercepted');
    }
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
    // Accessories intentionally scroll horizontally. Their own client area,
    // not the outer composer, must contain the full painted target height.
    const inAccessories = accessories.contains(el);
    return box.height < 43.5 || box.width < 43.5 || box.top < composerBox.top - .5 || box.bottom > composerBox.bottom + .5
      || (!inAccessories && (box.left < composerBox.left - .5 || box.right > composerBox.right + .5));
  })) failures.push('intake control clipped or smaller than 44px');
  const accessoryBox = accessories.getBoundingClientRect();
  const accessoryTop = accessoryBox.top + accessories.clientTop;
  const accessoryBottom = accessoryTop + accessories.clientHeight;
  if (accessoryBox.height > 0 && [...accessories.querySelectorAll('button')].some(el => {
    const box = el.getBoundingClientRect();
    return box.height > 0 && (box.height < 43.5 || box.top < accessoryTop - .5 || box.bottom > accessoryBottom + .5);
  })) failures.push('accessory targets clipped vertically');
  result.dataset.result = failures.length ? 'fail' : 'pass';
  result.textContent = `${failures.length ? `FAIL: ${failures.join('; ')}` : 'PASS: clear body, retained work/input, bounded diagnostics'}${focus ? ' (active Focus)' : ''}. CSS fixture only; no organism/backend/device proof.`;
}

function checkInitialIntake() {
  const failures = [];
  const composerBox = composer.getBoundingClientRect();
  for (let element = input; element && root.contains(element); element = element.parentElement) {
    const paint = getComputedStyle(element);
    if (paint.display === 'none' || paint.visibility !== 'visible' || Number(paint.opacity) < .99) {
      failures.push('intake is hidden by an initial presentation effect');
    }
  }
  for (const element of composer.querySelectorAll('input, button')) {
    const box = element.getBoundingClientRect();
    const accessoryOwner = element.closest('.gagos-bar__accessories');
    const accessoryBox = accessoryOwner?.getBoundingClientRect();
    // Desktop's display:contents wrapper has no clipping/scrolling box.
    // Only a painted scroll owner may replace the composer bounds.
    const scrollOwner = accessoryBox?.width > 0 && accessoryBox.height > 0
      && /^(auto|scroll|hidden|clip)$/.test(getComputedStyle(accessoryOwner).overflowX) ? accessoryOwner : null;
    const scrollBox = scrollOwner ? accessoryBox : null;
    const left = scrollBox ? scrollBox.left + scrollOwner.clientLeft : composerBox.left;
    const right = scrollBox ? left + scrollOwner.clientWidth : composerBox.right;
    const top = scrollBox ? scrollBox.top + scrollOwner.clientTop : composerBox.top;
    const bottom = scrollBox ? top + scrollOwner.clientHeight : composerBox.bottom;
    if (box.width < 43.5 || box.height < 43.5 || box.top < composerBox.top - .5 || box.bottom > composerBox.bottom + .5
      || box.top < top - .5 || box.bottom > bottom + .5 || box.top < -.5 || box.bottom > innerHeight + .5
      || (!scrollOwner && (box.left < composerBox.left - .5 || box.right > composerBox.right + .5))) failures.push('initial intake target clipped or below44px');
    // Optional accessories deliberately scroll horizontally. Offscreen ones
    // earn no hit-test credit; fully visible controls must retain edge hits.
    if (scrollOwner && (box.left < left - .5 || box.right > right + .5)) continue;
    const x = box.left + box.width / 2, y = box.top + box.height / 2;
    if ([[x, y], [box.left + 2, y], [box.right - 2, y], [x, box.top + 2], [x, box.bottom - 2]].some(([px, py]) => {
      const hit = document.elementFromPoint(px, py);
      return !hit || !element.contains(hit);
    })) failures.push('initial intake target hit intercepted');
  }
  result.dataset.result = failures.length ? 'fail' : 'pass';
  result.textContent = `${failures.length ? `FAIL: ${[...new Set(failures)].join('; ')}` : 'PASS: initial intake visible,44px targets and center/edge hits clear'}. Intake-only CSS clock-zero fixture; no header emergency Stop/startup latency/backend/device proof.`;
}

function checkRestingContact() {
  if (!(innerWidth >= 768 && innerHeight >= 360 && innerHeight <= 520)) {
    result.dataset.result = 'unavailable';
    result.textContent = 'Resting-contact check requires wide short360..520px layout. CSS only.';
    return;
  }
  const failures = [];
  checkDesktopControls(failures, true);
  const appBox = root.getBoundingClientRect();
  const bodyBox = scene.getBoundingClientRect();
  const composerBox = composer.getBoundingClientRect();
  const noticeBox = notice.getBoundingClientRect();
  const statusBox = status.getBoundingClientRect();
  if (getComputedStyle(root).getPropertyValue('--lm-short-rest-presence').trim() !== '1') failures.push('rest camera has no CSS-owned presence contract');
  if (appBox.height > innerHeight + .5) failures.push('rest controls escape short app');
  if (bodyBox.height < appBox.height * .6 || bodyBox.width < appBox.width * .35) failures.push('rest body has no substantial control-free pane');
  for (const element of root.querySelectorAll('.lm-stop, .gagos-experience-switch, .lm-navigation, .gagos-chat, .gagos-status, .lm-connection')) {
    if (overlaps(bodyBox, element.getBoundingClientRect())) failures.push('rest controls cover body pane');
  }
  if (!focus && (context.clientHeight < 31.5 || composerBox.top < navigation.getBoundingClientRect().bottom + 7.5)) failures.push('first-contact context starved or covered by navigation');
  if (!focus && context.scrollHeight > context.clientHeight + .5 && !['auto', 'scroll'].includes(getComputedStyle(context).overflowY)) failures.push('first-contact history clipped instead of scrollable');
  if (overlaps(composerBox, statusBox) || overlaps(composerBox, noticeBox) || overlaps(statusBox, noticeBox)) failures.push('rest intake/status/diagnostics overlap');
  if (noticeBox.bottom > appBox.bottom + .5 || composerBox.bottom > appBox.bottom + .5) failures.push('rest dock outside app');
  for (const element of root.querySelectorAll('.gagos-input, .gagos-send, .lm-stop > button, .gagos-experience-switch button')) {
    const box = element.getBoundingClientRect();
    if (box.width < 43.5 || box.height < 43.5) failures.push('first-contact target below44px');
    // Centre plus inset edge midpoints work for rounded/circular targets too.
    // An overlay that leaves only the centre reachable must not pass.
    const x = box.left + box.width / 2, y = box.top + box.height / 2;
    if ([[x, y], [box.left + 2, y], [box.right - 2, y], [x, box.top + 2], [x, box.bottom - 2]].some(([px, py]) => {
      const hit = document.elementFromPoint(px, py);
      return !hit || !element.contains(hit);
    })) failures.push('first-contact input/Send/Stop/mode hit intercepted');
    for (let ancestor = element.parentElement; ancestor && root.contains(ancestor); ancestor = ancestor.parentElement) {
      const parent = ancestor.getBoundingClientRect(), style = getComputedStyle(ancestor);
      const left = parent.left + ancestor.clientLeft, top = parent.top + ancestor.clientTop;
      if ((/^(auto|scroll|hidden|clip)$/.test(style.overflowX) && (box.left < left - .5 || box.right > left + ancestor.clientWidth + .5))
        || (/^(auto|scroll|hidden|clip)$/.test(style.overflowY) && (box.top < top - .5 || box.bottom > top + ancestor.clientHeight + .5))) failures.push('first-contact target clipped by ancestor');
    }
  }
  for (const scrollOwner of [accessories, status]) {
    const box = scrollOwner.getBoundingClientRect();
    const top = box.top + scrollOwner.clientTop;
    const bottom = top + scrollOwner.clientHeight;
    for (const button of scrollOwner.querySelectorAll('button')) {
      const target = button.getBoundingClientRect();
      if (target.width < 43.5 || target.height < 43.5 || target.top < top - .5 || target.bottom > bottom + .5) failures.push('rest scroll target undersized or vertically clipped');
    }
  }
  const retryBox = notice.querySelector('button').getBoundingClientRect();
  if (retryBox.width < 43.5 || retryBox.height < 43.5 || retryBox.left < noticeBox.left + notice.clientLeft - .5
    || retryBox.right > noticeBox.left + notice.clientLeft + notice.clientWidth + .5
    || retryBox.top < noticeBox.top + notice.clientTop - .5 || retryBox.bottom > noticeBox.top + notice.clientTop + notice.clientHeight + .5) failures.push('rest recovery target clipped');
  if (!failures.length && contextOverflow && !focus) {
    const last = context.lastElementChild.getBoundingClientRect(), viewport = context.getBoundingClientRect();
    if (context.scrollHeight <= context.clientHeight + .5) failures.push('fixture history does not stress scrolling');
    else if (context.scrollTop < 1 || last.bottom > viewport.top + context.clientTop + context.clientHeight + .5) {
      result.dataset.result = 'pending';
      result.textContent = 'Scroll the inert context to its last history line before this stress can PASS. CSS fixture only.';
      return;
    }
  }
  result.dataset.result = failures.length ? 'fail' : 'pass';
  result.textContent = `${failures.length ? `FAIL: ${[...new Set(failures)].join('; ')}` : 'PASS: first-contact hit targets, scrollable context, clear body and bounded truth'}${focus ? ' (resting Focus)' : ''}. CSS fixture only; no organism/backend/device proof.`;
}

function checkPhoneRest() {
  if (!(innerWidth >= 320 && innerWidth <= 767) || focus || guided || smallKeyboard) {
    result.dataset.result = 'unavailable';
    result.textContent = 'Phone rest check requires ordinary Expert320..767px composition. CSS only.';
    return;
  }
  const failures = [];
  const bodyBox = scene.getBoundingClientRect();
  const composerBox = composer.getBoundingClientRect();
  const noticeBox = notice.getBoundingClientRect();
  // The measured camera adapter trims header/edge clearance inside this
  // marker. Its lower space should reach the real intake, not stop at an
  // unrelated percentage while usable dark space remains.
  const unusedBodyRoom = composerBox.top - bodyBox.bottom;
  if (unusedBodyRoom < -.5 || unusedBodyRoom > 16.5) failures.push('rest presence wastes measured free height or covers intake');
  if (context.clientHeight < 63.5) failures.push('optional footer starves scrolling conversation');
  if (context.scrollHeight > context.clientHeight + .5 && !['auto', 'scroll'].includes(getComputedStyle(context).overflowY)) failures.push('rest history is not scrollable');
  if (noticeBox.top < composerBox.bottom + 7.5 || noticeBox.bottom > root.getBoundingClientRect().bottom + .5) failures.push('rest connection covers intake or escapes app');
  for (const element of root.querySelectorAll('.gagos-input, .gagos-send, .lm-stop > button, .gagos-experience-switch button')) {
    const box = element.getBoundingClientRect();
    if (box.width < 43.5 || box.height < 43.5 || box.top < -.5 || box.bottom > innerHeight + .5) failures.push('rest input/Send/Stop/mode target clipped or below44px');
    const x = box.left + box.width / 2, y = box.top + box.height / 2;
    if ([[x, y], [box.left + 2, y], [box.right - 2, y], [x, box.top + 2], [x, box.bottom - 2]].some(([px, py]) => {
      const hit = document.elementFromPoint(px, py);
      return !hit || !element.contains(hit);
    })) failures.push('rest input/Send/Stop/mode hit intercepted');
  }
  if (work !== root.querySelector('.lm-surface') || input !== root.querySelector('.gagos-input')) failures.push('retained work/input node replaced');
  result.dataset.result = failures.length ? 'fail' : 'pass';
  result.textContent = `${failures.length ? `FAIL: ${[...new Set(failures)].join('; ')}` : 'PASS: measured rest presence, scrolling conversation and clear44px controls'}. CSS fixture only; no organism/backend/device proof.`;
}

scheduleCheck();
window.addEventListener('resize', scheduleCheck);
notice.addEventListener('scroll', scheduleCheck);
navigation.addEventListener('toggle', scheduleCheck, true);
navigation.addEventListener('scroll', scheduleCheck);
accessories.addEventListener('scroll', scheduleCheck);
status.addEventListener('scroll', scheduleCheck);
context.addEventListener('scroll', scheduleCheck);
// Entrance transforms do not resize the bar. Retain any initial failure,
// but refresh the settled layout instead of caching that moving rectangle.
composer.addEventListener('animationend', scheduleCheck);
composer.addEventListener('animationcancel', scheduleCheck);
composer.addEventListener('transitionend', scheduleCheck);
const observer = new ResizeObserver(scheduleCheck);
for (const element of [scene, work, composer, notice, rail, status,
  root.querySelector('.lm-header'), root.querySelector('.gagos-experience-switch'), root.querySelector('.lm-navigation'),
  work.querySelector('.lm-surface__header'), work.querySelector('.lm-surface__content'), work.querySelector('.lm-surface__body'),
  composer.querySelector('.gagos-bar'), accessories, ...composer.querySelectorAll('input, button')]) observer.observe(element);
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
  navigation.removeEventListener('toggle', scheduleCheck, true);
  navigation.removeEventListener('scroll', scheduleCheck);
  accessories.removeEventListener('scroll', scheduleCheck);
  status.removeEventListener('scroll', scheduleCheck);
  context.removeEventListener('scroll', scheduleCheck);
  composer.removeEventListener('animationend', scheduleCheck);
  composer.removeEventListener('animationcancel', scheduleCheck);
  composer.removeEventListener('transitionend', scheduleCheck);
}, { once: true });
