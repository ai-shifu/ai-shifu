import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import AdminRowActions from './AdminRowActions';

jest.mock('@/components/ui/DropdownMenu', () => ({
  __esModule: true,
  DropdownMenu: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DropdownMenuTrigger: ({ children }: React.PropsWithChildren) => (
    <>{children}</>
  ),
  DropdownMenuContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DropdownMenuItem: ({
    children,
    disabled,
    onClick,
  }: React.PropsWithChildren<{
    disabled?: boolean;
    onClick?: () => void;
  }>) => (
    <button
      type='button'
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </button>
  ),
}));

describe('AdminRowActions', () => {
  test('renders visible actions and invokes the selected handler', () => {
    const edit = jest.fn();
    const remove = jest.fn();

    render(
      <AdminRowActions
        label='More'
        actions={[
          { key: 'edit', label: 'Edit', onClick: edit },
          { key: 'hidden', label: 'Hidden', onClick: jest.fn(), hidden: true },
          { key: 'remove', label: 'Remove', onClick: remove },
        ]}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));

    expect(edit).toHaveBeenCalledTimes(1);
    expect(remove).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Hidden' })).toBeNull();
  });

  test('keeps disabled actions visible without invoking handlers', () => {
    const grant = jest.fn();

    render(
      <AdminRowActions
        label='More'
        ariaLabel='More for user'
        actions={[
          {
            key: 'grant',
            label: 'Grant credits',
            onClick: grant,
            disabled: true,
          },
        ]}
      />,
    );

    expect(screen.getByRole('button', { name: 'More for user' })).toBeEnabled();
    expect(
      screen.getByRole('button', { name: 'Grant credits' }),
    ).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Grant credits' }));

    expect(grant).not.toHaveBeenCalled();
  });

  test('renders nothing when every action is hidden', () => {
    const { container } = render(
      <AdminRowActions
        label='More'
        actions={[
          { key: 'hidden', label: 'Hidden', onClick: jest.fn(), hidden: true },
        ]}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
