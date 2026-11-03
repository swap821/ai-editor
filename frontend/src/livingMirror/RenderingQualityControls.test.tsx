import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { RenderingQualityControls } from './RenderingQualityControls';

const useOwner = vi.hoisted(() => vi.fn());

vi.mock('../superbrain/components/qualityTierContext', () => ({
  useQualityTierOwner: () => useOwner(),
}));

beforeEach(() => {
  useOwner.mockReset();
});

afterEach(() => {
  cleanup();
});

it('renders nothing when there is no quality tier owner', () => {
  useOwner.mockReturnValue(null);
  const { container } = render(<RenderingQualityControls />);
  expect(container).toBeEmptyDOMElement();
});

it('shows the Auto preference with its four choices and the adaptive help text', () => {
  useOwner.mockReturnValue({ preference: 'auto', setTier: vi.fn() });
  render(<RenderingQualityControls />);

  expect(screen.getByRole('group', { name: 'Rendering preferences' })).toBeInTheDocument();
  const select = screen.getByLabelText('Visual detail') as HTMLSelectElement;
  expect(select).toHaveValue('auto');
  expect(Array.from(select.options).map((o) => [o.value, o.textContent])).toEqual([
    ['auto', 'Auto'],
    ['high', 'High detail'],
    ['medium', 'Balanced'],
    ['low', 'Economy'],
  ]);

  const helpId = select.getAttribute('aria-describedby') ?? '';
  expect(document.getElementById(helpId)).toHaveTextContent(
    'Optional detail adapts to frame pacing. Work and controls stay intact.',
  );
});

it('reflects a manual preference and switches to the manual help text', () => {
  useOwner.mockReturnValue({ preference: 'medium', setTier: vi.fn() });
  render(<RenderingQualityControls />);

  const select = screen.getByLabelText('Visual detail');
  expect(select).toHaveValue('medium');
  const helpId = select.getAttribute('aria-describedby') ?? '';
  expect(document.getElementById(helpId)).toHaveTextContent(
    'Manual detail; resolution adapts within its limits.',
  );
  expect(
    screen.queryByText('Optional detail adapts to frame pacing. Work and controls stay intact.'),
  ).not.toBeInTheDocument();
});

it('passes the chosen preference to the owner', () => {
  const setTier = vi.fn();
  useOwner.mockReturnValue({ preference: 'auto', setTier });
  render(<RenderingQualityControls />);

  fireEvent.change(screen.getByLabelText('Visual detail'), { target: { value: 'low' } });

  expect(setTier).toHaveBeenCalledTimes(1);
  expect(setTier).toHaveBeenCalledWith('low');
});
