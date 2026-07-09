import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import BudgetMicroBar from './BudgetMicroBar';
import React from 'react';

describe('BudgetMicroBar', () => {
  it('renders correctly', () => {
    render(<BudgetMicroBar />);
    expect(screen.getByText('$12.50')).toBeInTheDocument();
  });

  it('expands to show breakdown', () => {
    render(<BudgetMicroBar />);
    
    // Initially not expanded
    expect(screen.queryByText('Daily Allowance')).not.toBeInTheDocument();
    
    // Click to expand
    fireEvent.click(screen.getByText('$12.50'));
    
    // Should show breakdown
    expect(screen.getByText('Daily Allowance')).toBeInTheDocument();
    expect(screen.getByText('$50.00')).toBeInTheDocument();
    expect(screen.getByText('plan')).toBeInTheDocument();
    expect(screen.getByText('$2.10')).toBeInTheDocument();
  });
});
