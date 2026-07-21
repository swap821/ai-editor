import { render, screen } from '@testing-library/react';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import MobileHUD from './MobileHUD';

describe('MobileHUD', () => {
  let originalInnerWidth;

  beforeEach(() => {
    originalInnerWidth = window.innerWidth;
  });

  afterEach(() => {
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: originalInnerWidth
    });
  });

  it('renders children normally on desktop', () => {
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: 1024
    });

    render(
      <MobileHUD>
        <div data-testid="desktop-child">Desktop</div>
      </MobileHUD>
    );

    expect(screen.getByTestId('desktop-child')).toBeInTheDocument();
    expect(screen.queryByTestId('mobile-hud')).not.toBeInTheDocument();
  });

  it('renders mobile wrapper on mobile screens', () => {
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: 375
    });

    render(
      <MobileHUD>
        <div data-testid="mobile-child">Child</div>
      </MobileHUD>
    );

    expect(screen.getByTestId('mobile-hud')).toBeInTheDocument();
    expect(screen.getByText('Mobile Operator Interface')).toBeInTheDocument();
  });
});
