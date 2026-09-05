import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import { AlertProvider } from '@/components/ui/UseAlert';
import Header from './Header';

const mockSaveMdflow = jest.fn();
const mockToast = jest.fn();
const mockTrackEvent = jest.fn();
const mockCurrentShifu = {
  bid: 'course-1',
  name: 'Published Course',
  description: 'A teacher-written course description.',
  canPublish: true,
  readonly: false,
  url: 'https://example.test/c/course-1',
  tts_enabled: true,
};

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
    currentShifu: mockCurrentShifu,
    actions: {
      saveMdflow: mockSaveMdflow,
      loadShifu: jest.fn(),
    },
  }),
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({
    toast: mockToast,
  }),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({
    trackEvent: mockTrackEvent,
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
    mockToast.mockReset();
    mockTrackEvent.mockReset();
    mockCurrentShifu.name = 'Published Course';
    mockCurrentShifu.description = 'A teacher-written course description.';
    mockCurrentShifu.canPublish = true;
    mockCurrentShifu.readonly = false;
    mockCurrentShifu.url = 'https://example.test/c/course-1';
    (api.publishShifu as jest.Mock).mockReset();
    Object.defineProperty(navigator, 'share', {
      configurable: true,
      value: undefined,
    });
    Object.defineProperty(navigator, 'canShare', {
      configurable: true,
      value: undefined,
    });
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: jest.fn().mockResolvedValue(undefined),
      },
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  const expectNoRejectedLearningLink = () => {
    expect(
      screen.queryByRole('button', {
        name: 'component.header.copyLearningLink',
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('component.header.learningLink'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'javascript:alert(1)' }),
    ).not.toBeInTheDocument();
    for (const link of screen.queryAllByRole('link', { hidden: true })) {
      const href = link.getAttribute('href');
      expect(href).toBeTruthy();
      expect(href).not.toMatch(/^javascript:/i);
    }
  };

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
    expect(mockTrackEvent).toHaveBeenCalledWith('creator_publish_attempt', {
      shifu_bid: 'course-1',
      learning_mode: 'default',
    });
    expect(mockTrackEvent).toHaveBeenCalledWith('creator_publish_result', {
      shifu_bid: 'course-1',
      learning_mode: 'default',
      outcome: 'success',
    });
    const eventNames = mockTrackEvent.mock.calls.map(([name]) => name);
    expect(eventNames).not.toContain('creator_publish_click');
    expect(eventNames).not.toContain('creator_publish_confirm');
  });

  test('records save and publish failures as one terminal result', async () => {
    mockSaveMdflow.mockRejectedValueOnce(new Error('private save failure'));

    renderHeader();
    fireEvent.click(
      screen.getByRole('button', { name: 'component.header.publish' }),
    );

    await waitFor(() => {
      expect(mockTrackEvent).toHaveBeenCalledWith('creator_publish_result', {
        shifu_bid: 'course-1',
        learning_mode: 'default',
        outcome: 'failed',
        failure_stage: 'save',
      });
    });
    expect(api.publishShifu).not.toHaveBeenCalled();
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private save failure',
    );
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'component.header.publish' }),
      ).toBeEnabled();
    });

    mockTrackEvent.mockReset();
    mockSaveMdflow.mockResolvedValueOnce(undefined);
    (api.publishShifu as jest.Mock).mockRejectedValueOnce(
      new Error('private publish failure'),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'component.header.publish' }),
    );

    await waitFor(() => {
      expect(mockTrackEvent).toHaveBeenCalledWith('creator_publish_result', {
        shifu_bid: 'course-1',
        learning_mode: 'default',
        outcome: 'failed',
        failure_stage: 'publish',
      });
    });
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private publish failure',
    );
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

  test('omits the learning link when the published URL is rejected', async () => {
    (api.publishShifu as jest.Mock).mockResolvedValue('javascript:alert(1)');

    renderHeader();
    fireEvent.click(
      screen.getByRole('button', { name: 'component.header.publish' }),
    );

    await screen.findByText('component.header.publishSuccess');
    expectNoRejectedLearningLink();
  });

  test('closes the pending tab instead of navigating when the published URL is rejected', async () => {
    const pendingWindow = {
      closed: false,
      close: jest.fn(function closePendingWindow() {
        this.closed = true;
      }),
      location: { href: 'about:blank' },
      opener: {} as Window | null,
    };
    const openSpy = jest
      .spyOn(window, 'open')
      .mockReturnValue(pendingWindow as unknown as Window);
    (api.publishShifu as jest.Mock).mockResolvedValue('javascript:alert(1)');

    renderHeader();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'component.header.publishAndOpenListenMode',
      }),
    );

    await waitFor(() => {
      expect(pendingWindow.close).toHaveBeenCalled();
    });
    expect(pendingWindow.location.href).toBe('about:blank');
    expect(openSpy).toHaveBeenCalledTimes(1);
    expect(openSpy).toHaveBeenCalledWith('about:blank', '_blank');
    await screen.findByText('component.header.publishSuccess');
    expectNoRejectedLearningLink();
  });

  test('does not copy a rejected published URL for a learning mode', async () => {
    mockCurrentShifu.url = 'javascript:alert(1)';

    renderHeader();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'component.header.copyListenModeLink',
      }),
    );

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith({
        title: 'component.header.copyLinkFailed',
        variant: 'destructive',
      });
    });
    expect(navigator.clipboard.writeText).not.toHaveBeenCalled();
  });

  test('shares an unpublished read-only course without publish permission', async () => {
    mockCurrentShifu.canPublish = false;
    mockCurrentShifu.readonly = true;
    mockCurrentShifu.url = '';

    renderHeader();

    const shareButton = screen.getByRole('button', {
      name: 'common.core.shareCourse',
    });
    expect(shareButton).toBeEnabled();
    expect(
      screen.getByRole('button', { name: 'component.header.publish' }),
    ).toBeDisabled();

    fireEvent.click(shareButton);
    fireEvent.click(
      screen.getByRole('button', {
        name: 'common.core.shareIntroductionAndLink',
      }),
    );

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        expect.stringContaining(`${window.location.origin}/c/course-1`),
      );
    });
    expect(api.publishShifu).not.toHaveBeenCalled();
    expect(mockSaveMdflow).not.toHaveBeenCalled();
  });

  test('sanitizes the teacher course URL before native sharing', async () => {
    mockCurrentShifu.url =
      'https://user:secret@courses.example.test/c/course-1?lessonid=lesson-2&mode=listen&preview=true#outline';
    const nativeShare = jest.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'share', {
      configurable: true,
      value: nativeShare,
    });

    renderHeader();
    fireEvent.click(
      screen.getByRole('button', { name: 'common.core.shareCourse' }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'common.core.shareIntroductionAndLink',
      }),
    );

    await waitFor(() => {
      expect(nativeShare).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Published Course',
          url: 'https://courses.example.test/c/course-1',
        }),
      );
    });
    expect(api.publishShifu).not.toHaveBeenCalled();
  });

  test.each([
    'javascript:alert(1)',
    'not-a-url',
    '?preview=true',
    '//evil.example.test/c/another-course',
  ])(
    'falls back to the current course path when the teacher URL is unsafe: %s',
    async unsafeUrl => {
      mockCurrentShifu.url = unsafeUrl;
      const nativeShare = jest.fn().mockResolvedValue(undefined);
      Object.defineProperty(navigator, 'share', {
        configurable: true,
        value: nativeShare,
      });

      renderHeader();
      fireEvent.click(
        screen.getByRole('button', { name: 'common.core.shareCourse' }),
      );
      fireEvent.click(
        screen.getByRole('button', {
          name: 'common.core.shareIntroductionAndLink',
        }),
      );

      await waitFor(() => {
        expect(nativeShare).toHaveBeenCalledWith(
          expect.objectContaining({
            url: `${window.location.origin}/c/course-1`,
          }),
        );
      });
      expect(api.publishShifu).not.toHaveBeenCalled();
    },
  );
});
