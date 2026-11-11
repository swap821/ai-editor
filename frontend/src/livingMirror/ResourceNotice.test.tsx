import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ResourceNotice } from './ResourceNotice';

type Props = ComponentProps<typeof ResourceNotice>;

function makeResource(overrides: Record<string, unknown> = {}): Props['resource'] {
  return {
    data: null,
    status: 'available',
    error: null,
    receivedAt: null,
    refresh: vi.fn(),
    ...overrides,
  } as unknown as Props['resource'];
}

afterEach(() => {
  cleanup();
});

describe('ResourceNotice', () => {
  it('shows a loading message and disables refresh while first loading', () => {
    render(<ResourceNotice resource={makeResource({ status: 'loading' })} empty="Nothing here" />);

    const notice = screen.getByRole('status');
    expect(notice.textContent).toContain('Loading records…');
    expect(notice.textContent).not.toContain('Refreshing last-known records…');
    expect((screen.getByRole('button', { name: 'Refresh' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('says it is refreshing last-known records when loading with existing data', () => {
    render(
      <ResourceNotice
        resource={makeResource({ status: 'loading', data: [1], receivedAt: 1700000000000 })}
        empty="Nothing here"
      />,
    );

    const notice = screen.getByRole('status');
    expect(notice.textContent).toContain('Refreshing last-known records…');
    expect(notice.textContent).toContain(' · stale');
  });

  it('shows the empty message when the resource is empty and not stale', () => {
    render(<ResourceNotice resource={makeResource({ status: 'empty', data: [] })} empty="Nothing here" />);

    const notice = screen.getByRole('status');
    expect(notice.textContent).toContain('Nothing here');
    expect(notice.textContent).not.toContain('stale');
    expect((screen.getByRole('button', { name: 'Refresh' }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('shows the error and a last-known warning when data is retained', () => {
    render(
      <ResourceNotice
        resource={makeResource({ status: 'error', data: [1], error: 'Service down' })}
        empty="Nothing here"
      />,
    );

    const notice = screen.getByRole('status');
    expect(notice.textContent).toContain('Service down');
    expect(notice.textContent).toContain('The records below are last-known.');
  });

  it('omits the last-known warning when there is no data', () => {
    render(<ResourceNotice resource={makeResource({ status: 'error', error: 'Service down' })} empty="x" />);

    const notice = screen.getByRole('status');
    expect(notice.textContent).toContain('Service down');
    expect(notice.textContent).not.toContain('last-known');
  });

  it('shows the received time, marking it stale only when stale', () => {
    const receivedAt = 1700000000000;
    const formatted = new Date(receivedAt).toLocaleString();

    render(
      <ResourceNotice resource={makeResource({ data: [1], receivedAt })} empty="x" />,
    );
    expect(screen.getByText(`Received ${formatted}`).tagName).toBe('SMALL');
    cleanup();

    render(
      <ResourceNotice resource={makeResource({ status: 'error', data: [1], receivedAt })} empty="x" />,
    );
    expect(screen.getByText(`Received ${formatted} · stale`)).toBeTruthy();
  });

  it('calls refresh when the button is clicked', () => {
    const refresh = vi.fn();
    render(<ResourceNotice resource={makeResource({ refresh })} empty="x" />);

    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));

    expect(refresh).toHaveBeenCalledTimes(1);
  });
});
