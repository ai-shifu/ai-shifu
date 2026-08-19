import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import api from '@/api';
import { AlertProvider } from '@/components/ui/UseAlert';
import Header from './Header';

const mockSaveMdflow = jest.fn();

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    publishShifu: jest.fn(),
  },
}));

jest.mock('@/store', () => ({
  useShifu: () => ({
    isSaving: false,
    error: null,
    currentShifu: {
      bid: 'course-1',
      name: 'Published Course',
      canPublish: true,
      url: 'https://example.test/c/course-1',
      tts_enabled: true,
    },
    actions: {
      saveMdflow: mockSaveMdflow,
      loadShifu: jest.fn(),
    },
  }),
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({
    toast: jest.fn(),
  }),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({
    trackEvent: jest.fn(),
  }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({
    children,
    href,
    ...props
  }: React.ComponentProps<'a'> & { href: string }) => (
    <a
      href={href}
      {...props}
    >
      {children}
    </a>
  ),
}));

jest.mock('@/components/preview', () => ({
  __esModule: true,
  default: () => <div data-testid='preview' />,
}));

jest.mock('@/components/shifu-setting', () => ({
  __esModule: true,
  default: () => <div data-testid='shifu-setting' />,
}));

jest.mock('@/components/ui/DropdownMenu', () => ({
  DropdownMenu: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DropdownMenuTrigger: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DropdownMenuContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DropdownMenuItem: ({
    children,
    onSelect,
    disabled,
  }: React.PropsWithChildren<{
    onSelect?: () => void;
    disabled?: boolean;
  }>) => {
    if (!React.isValidElement(children)) {
      return (
        <button
          type='button'
          disabled={disabled}
          onClick={() => {
            onSelect?.();
          }}
        >
          {children}
        </button>
      );
    }

    const child = children as React.ReactElement<{
      onClick?: React.MouseEventHandler<HTMLElement>;
      disabled?: boolean;
    }>;

    return React.cloneElement(child, {
      disabled: Boolean(disabled || child.props.disabled),
      onClick: (event: React.MouseEvent<HTMLElement>) => {
        child.props.onClick?.(event);
        if (!disabled) {
          onSelect?.();
        }
      },
    });
  },
}));

const renderHeader = () =>
  render(
    <AlertProvider>
      <Header />
    </AlertProvider>,
  );

describe('Header publish success link', () => {
  beforeEach(() => {
    mockSaveMdflow.mockReset().mockResolvedValue(undefined);
    (api.publishShifu as jest.Mock).mockReset();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test('shows a parameterless learning link after publishing', async () => {
    (api.publishShifu as jest.Mock).mockResolvedValue(
      'https://example.test/c/course-1?mode=listen&lessonid=lesson-2#outline',
    );

    renderHeader();

    fireEvent.click(
      screen.getByRole('button', { name: 'component.header.publish' }),
    );

    const learningLink = await screen.findByRole('link', {
      name: 'https://example.test/c/course-1',
    });
    expect(learningLink).toHaveAttribute(
      'href',
      'https://example.test/c/course-1',
    );
    expect(learningLink.getAttribute('href')).not.toContain('?');
  });

  test('keeps the success dialog link parameterless when opening a learning mode fails', async () => {
    (api.publishShifu as jest.Mock).mockResolvedValue(
      'https://example.test/c/course-1',
    );
    jest.spyOn(window, 'open').mockReturnValue(null);

    renderHeader();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'component.header.publishAndOpenClassroomMode',
      }),
    );

    const learningLink = await screen.findByRole('link', {
      name: 'https://example.test/c/course-1',
    });
    expect(learningLink).toHaveAttribute(
      'href',
      'https://example.test/c/course-1',
    );
    expect(learningLink.getAttribute('href')).not.toContain('mode=');
  });
});
