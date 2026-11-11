import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { PersistentWorkspaceBody } from './PersistentWorkspaceBody';

afterEach(cleanup);

function body(): HTMLElement {
  const element = screen.getByTestId('child').closest('.lm-surface__body');
  if (!(element instanceof HTMLElement)) throw new Error('body element not found');
  return element;
}

describe('PersistentWorkspaceBody', () => {
  it('renders nothing until the view has been selected', () => {
    render(
      <PersistentWorkspaceBody selected={false} visible={false}>
        <span data-testid="child">content</span>
      </PersistentWorkspaceBody>,
    );
    expect(screen.queryByTestId('child')).toBeNull();
  });

  it('keeps children mounted but hidden after the view is deselected', () => {
    const { rerender } = render(
      <PersistentWorkspaceBody selected visible className="extra">
        <span data-testid="child">content</span>
      </PersistentWorkspaceBody>,
    );
    const first = body();
    expect(first.className).toBe('lm-surface__body extra');
    expect(first.hidden).toBe(false);

    rerender(
      <PersistentWorkspaceBody selected={false} visible={false} className="extra">
        <span data-testid="child">content</span>
      </PersistentWorkspaceBody>,
    );
    const second = body();
    expect(second).toBe(first);
    expect(second.hidden).toBe(true);
    expect(second.hasAttribute('inert')).toBe(true);
  });

  it('omits trailing whitespace from the class name by default', () => {
    render(
      <PersistentWorkspaceBody selected visible>
        <span data-testid="child">content</span>
      </PersistentWorkspaceBody>,
    );
    expect(body().className).toBe('lm-surface__body');
  });

  it('restores the last visible scroll position and ignores hidden scroll events', () => {
    const { rerender } = render(
      <PersistentWorkspaceBody selected visible>
        <span data-testid="child">content</span>
      </PersistentWorkspaceBody>,
    );
    const element = body();
    element.scrollTop = 50;
    element.scrollLeft = 7;
    fireEvent.scroll(element);

    rerender(
      <PersistentWorkspaceBody selected visible={false}>
        <span data-testid="child">content</span>
      </PersistentWorkspaceBody>,
    );
    element.scrollTop = 0;
    element.scrollLeft = 0;
    fireEvent.scroll(element);

    rerender(
      <PersistentWorkspaceBody selected visible>
        <span data-testid="child">content</span>
      </PersistentWorkspaceBody>,
    );
    expect(element.scrollTop).toBe(50);
    expect(element.scrollLeft).toBe(7);
  });
});
