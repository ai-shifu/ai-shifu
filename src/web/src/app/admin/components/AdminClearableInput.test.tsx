import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import AdminClearableInput from './AdminClearableInput';

describe('AdminClearableInput', () => {
  test('shows a clear button with the provided aria-label and clears the value', () => {
    const handleChange = jest.fn();

    render(
      <AdminClearableInput
        value='Order 123'
        placeholder='Search orders'
        clearLabel='Clear search'
        onChange={handleChange}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Clear search' }));

    expect(handleChange).toHaveBeenCalledWith('');
  });

  test('hides the clear button for nullish values', () => {
    render(
      <AdminClearableInput
        value={null}
        placeholder='Search orders'
        clearLabel='Clear search'
        onChange={() => undefined}
      />,
    );

    expect(
      screen.queryByRole('button', { name: 'Clear search' }),
    ).not.toBeInTheDocument();
  });

  test('submits on Enter when composition is inactive', () => {
    const handleSubmit = jest.fn();

    render(
      <AdminClearableInput
        value='keyword'
        placeholder='Search orders'
        clearLabel='Clear search'
        onChange={() => undefined}
        onSubmit={handleSubmit}
      />,
    );

    fireEvent.keyDown(screen.getByRole('textbox'), {
      key: 'Enter',
      nativeEvent: { isComposing: false },
    });

    expect(handleSubmit).toHaveBeenCalledTimes(1);
  });

  test('does not submit on Enter while IME composition is active', () => {
    const handleSubmit = jest.fn();

    render(
      <AdminClearableInput
        value='关键词'
        placeholder='Search orders'
        clearLabel='Clear search'
        onChange={() => undefined}
        onSubmit={handleSubmit}
      />,
    );

    fireEvent.keyDown(screen.getByRole('textbox'), {
      key: 'Enter',
      isComposing: true,
    });

    expect(handleSubmit).not.toHaveBeenCalled();
  });
});
