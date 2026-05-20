import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import AdminTooltipText from './AdminTooltipText';

class MockResizeObserver {
  observe() {}
  disconnect() {}
}

class MockMutationObserver {
  private callback: MutationCallback;

  constructor(callback: MutationCallback) {
    this.callback = callback;
  }

  observe() {}

  disconnect() {}

  trigger() {
    this.callback([], this as unknown as MutationObserver);
  }
}

jest.mock('@/components/ui/tooltip', () => ({
  __esModule: true,
  Tooltip: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TooltipTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TooltipContent: ({ children }: React.PropsWithChildren) => (
    <div data-testid='tooltip-content'>{children}</div>
  ),
}));

describe('AdminTooltipText', () => {
  let mutationObserver: MockMutationObserver | null = null;

  beforeEach(() => {
    mutationObserver = null;
    Object.defineProperty(window, 'ResizeObserver', {
      configurable: true,
      writable: true,
      value: MockResizeObserver,
    });
    Object.defineProperty(window, 'MutationObserver', {
      configurable: true,
      writable: true,
      value: class extends MockMutationObserver {
        constructor(callback: MutationCallback) {
          super(callback);
          mutationObserver = this;
        }
      },
    });
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
      configurable: true,
      get() {
        const text = this.textContent?.trim() ?? '';
        return text === 'Long content value' ? 80 : 120;
      },
    });
    Object.defineProperty(HTMLElement.prototype, 'scrollWidth', {
      configurable: true,
      get() {
        const text = this.textContent?.trim() ?? '';
        return text === 'Long content value' ? 160 : 120;
      },
    });
    Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
      configurable: true,
      get() {
        return 20;
      },
    });
    Object.defineProperty(HTMLElement.prototype, 'scrollHeight', {
      configurable: true,
      get() {
        return 20;
      },
    });
  });

  test('renders tooltip content only when text overflows', async () => {
    render(
      <AdminTooltipText
        text='Long content value'
        emptyValue='--'
      />,
    );

    await waitFor(() => {
      expect(screen.getAllByText('Long content value')).toHaveLength(2);
    });
    expect(screen.getByTestId('tooltip-content')).toHaveTextContent(
      'Long content value',
    );
  });

  test('falls back to the provided empty value', () => {
    render(
      <AdminTooltipText
        text='   '
        emptyValue='-'
      />,
    );

    expect(screen.getByText('-')).toBeInTheDocument();
    expect(screen.queryByTestId('tooltip-content')).not.toBeInTheDocument();
  });

  test('trims surrounding whitespace before rendering', () => {
    render(
      <AdminTooltipText
        text='  Course One  '
        emptyValue='--'
      />,
    );

    expect(screen.getByText('Course One')).toBeInTheDocument();
    expect(screen.queryByTestId('tooltip-content')).not.toBeInTheDocument();
    expect(screen.queryByText('  Course One  ')).not.toBeInTheDocument();
  });

  test('updates overflow state when display text changes without changing value', async () => {
    const { rerender } = render(
      <AdminTooltipText
        text='Stable tooltip value'
        displayText='Short label'
        emptyValue='--'
      />,
    );

    expect(screen.getByText('Short label')).toBeInTheDocument();
    expect(screen.queryByTestId('tooltip-content')).not.toBeInTheDocument();

    rerender(
      <AdminTooltipText
        text='Stable tooltip value'
        displayText='Long content value'
        emptyValue='--'
      />,
    );

    act(() => {
      mutationObserver?.trigger();
    });

    await waitFor(() => {
      expect(screen.getByTestId('tooltip-content')).toHaveTextContent(
        'Stable tooltip value',
      );
    });
  });
});
