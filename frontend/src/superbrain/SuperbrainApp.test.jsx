import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SuperbrainApp from './SuperbrainApp';

const mocks = vi.hoisted(() => ({
  startMirrorClient: vi.fn(),
  stopMirrorClient: vi.fn(),
  writeExperienceMode: vi.fn(),
}));

vi.mock('../workbench/GagosChrome', () => ({
  default: (props) => (
    <div data-testid="chrome" data-integrated={String(props.integrated)}>
      <input aria-label="Talk to GAGOS" />
      <button className="lm-stop__engage" type="button">stop</button>
      <button type="button" onClick={() => props.onExperienceModeChange('changed')}>change-mode</button>
      <button type="button" onClick={() => props.onInputAttentionChange(true)}>attend</button>
      <button type="button" onClick={() => props.onInputAttentionChange(false)}>unattend</button>
    </div>
  ),
}));

vi.mock('../livingMirror/experienceMode', () => ({
  readExperienceMode: () => 'initial',
  writeExperienceMode: mocks.writeExperienceMode,
}));

vi.mock('./lib/aiosMirror', () => ({
  startMirrorClient: mocks.startMirrorClient,
  stopMirrorClient: mocks.stopMirrorClient,
}));

vi.mock('../workbench/OrganismScene', () => ({
  default: (props) => (
    <div data-testid="scene" data-booted={String(props.booted)}>
      <button type="button" onClick={props.onBootComplete}>finish-boot</button>
    </div>
  ),
}));

function appRoot(container) {
  const root = container.querySelector('.lm-app');
  if (!root) throw new Error('app root missing');
  return root;
}

describe('SuperbrainApp', () => {
  beforeEach(() => {
    mocks.startMirrorClient.mockReset();
    mocks.stopMirrorClient.mockReset();
    mocks.writeExperienceMode.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it('renders the integrated chrome inside the conversation landmark', () => {
    render(<SuperbrainApp />);
    const main = screen.getByRole('main', { name: 'GAGOS conversation' });
    const chrome = screen.getByTestId('chrome');
    expect(main.contains(chrome)).toBe(true);
    expect(chrome.getAttribute('data-integrated')).toBe('true');
  });

  it('starts from the stored experience mode and idle working state', () => {
    const { container } = render(<SuperbrainApp />);
    const root = appRoot(container);
    expect(root.getAttribute('data-experience-mode')).toBe('initial');
    expect(root.getAttribute('data-working')).toBe('false');
  });

  it('persists and applies an experience mode chosen in the chrome', () => {
    const { container } = render(<SuperbrainApp />);
    fireEvent.click(screen.getByText('change-mode'));
    expect(mocks.writeExperienceMode).toHaveBeenCalledWith('changed');
    expect(appRoot(container).getAttribute('data-experience-mode')).toBe('changed');
  });

  it('starts the mirror client on mount and stops it on unmount', () => {
    const { unmount } = render(<SuperbrainApp />);
    expect(mocks.startMirrorClient).toHaveBeenCalledTimes(1);
    expect(mocks.stopMirrorClient).not.toHaveBeenCalled();
    unmount();
    expect(mocks.stopMirrorClient).toHaveBeenCalledTimes(1);
  });

  it('passes booted=false to the scene until the scene reports boot complete', async () => {
    render(<SuperbrainApp />);
    const scene = await screen.findByTestId('scene');
    expect(scene.getAttribute('data-booted')).toBe('false');
    fireEvent.click(screen.getByText('finish-boot'));
    expect(screen.getByTestId('scene').getAttribute('data-booted')).toBe('true');
  });

  it('marks the scene booted when input attention becomes active and keeps it booted afterwards', async () => {
    render(<SuperbrainApp />);
    await screen.findByTestId('scene');
    fireEvent.click(screen.getByText('attend'));
    expect(screen.getByTestId('scene').getAttribute('data-booted')).toBe('true');
    fireEvent.click(screen.getByText('unattend'));
    expect(screen.getByTestId('scene').getAttribute('data-booted')).toBe('true');
  });

  it('flags controls ready and announces it once the input and stop control exist', () => {
    vi.useFakeTimers({ toFake: ['requestAnimationFrame', 'cancelAnimationFrame'] });
    const onReady = vi.fn();
    window.addEventListener('gagos:controls-ready', onReady);
    const { container } = render(<SuperbrainApp />);
    act(() => {
      vi.advanceTimersByTime(100);
    });
    window.removeEventListener('gagos:controls-ready', onReady);
    expect(appRoot(container).getAttribute('data-controls-ready')).toBe('true');
    expect(onReady).toHaveBeenCalledTimes(1);
  });
});
