import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import PanelLauncher from './PanelLauncher';
import React from 'react';

describe('PanelLauncher', () => {
  it('is collapsed by default and shows no panel list', () => {
    render(<PanelLauncher panels={[{ name: 'File Tree', isOpen: true, setOpen: vi.fn() }]} />);
    expect(screen.queryByText('File Tree')).not.toBeInTheDocument();
  });

  it('lists every panel with its current open state on click', () => {
    render(
      <PanelLauncher
        panels={[
          { name: 'File Tree', isOpen: true, setOpen: vi.fn() },
          { name: 'Settings', isOpen: false, setOpen: vi.fn() },
        ]}
      />
    );

    fireEvent.click(screen.getByLabelText('Reopen a closed panel'));

    expect(screen.getByText('File Tree')).toBeInTheDocument();
    expect(screen.getByText('Settings')).toBeInTheDocument();
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes[0]).toBeChecked();
    expect(checkboxes[1]).not.toBeChecked();
  });

  it('reopens a closed panel via its checkbox -- the actual missing affordance', () => {
    const setSettingsOpen = vi.fn();
    render(
      <PanelLauncher
        panels={[{ name: 'Settings', isOpen: false, setOpen: setSettingsOpen }]}
      />
    );

    fireEvent.click(screen.getByLabelText('Reopen a closed panel'));
    fireEvent.click(screen.getByRole('checkbox'));

    expect(setSettingsOpen).toHaveBeenCalledWith(true);
  });

  it('closes an open panel via its checkbox too', () => {
    const setFileTreeOpen = vi.fn();
    render(
      <PanelLauncher
        panels={[{ name: 'File Tree', isOpen: true, setOpen: setFileTreeOpen }]}
      />
    );

    fireEvent.click(screen.getByLabelText('Reopen a closed panel'));
    fireEvent.click(screen.getByRole('checkbox'));

    expect(setFileTreeOpen).toHaveBeenCalledWith(false);
  });
});
