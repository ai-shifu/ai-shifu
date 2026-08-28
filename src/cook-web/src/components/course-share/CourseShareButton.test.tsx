import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';

import { CourseShareButton } from './CourseShareButton';

const mockToast = jest.fn();
const mockTrackEvent = jest.fn();

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) => {
      if (key === 'common.core.share') {
        return 'Share';
      }
      if (key === 'common.core.shareCourse') {
        return 'Share course';
      }
      if (key === 'common.core.shareCourseMessage') {
        return `Recommend ${String(values?.courseName)}`;
      }
      if (key === 'common.core.shareContentCopied') {
        return 'Share content copied';
      }
      if (key === 'common.core.shareFailed') {
        return 'Unable to share';
      }
      return key;
    },
  }),
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

const originalShare = Object.getOwnPropertyDescriptor(navigator, 'share');
const originalCanShare = Object.getOwnPropertyDescriptor(navigator, 'canShare');
const originalClipboard = Object.getOwnPropertyDescriptor(
  navigator,
  'clipboard',
);

const restoreNavigatorProperty = (
  property: 'share' | 'canShare' | 'clipboard',
  descriptor: PropertyDescriptor | undefined,
) => {
  if (descriptor) {
    Object.defineProperty(navigator, property, descriptor);
  } else {
    delete (navigator as unknown as Record<string, unknown>)[property];
  }
};

const setNavigatorProperty = (
  property: 'share' | 'canShare' | 'clipboard',
  value: unknown,
) => {
  Object.defineProperty(navigator, property, {
    configurable: true,
    value,
  });
};

const renderShareButton = (
  overrides: Partial<React.ComponentProps<typeof CourseShareButton>> = {},
) =>
  render(
    <CourseShareButton
      courseTitle='Practical AI'
      courseDescription='  A hands-on course.  '
      shifuBid='course-1'
      resolveShareUrl={() =>
        'https://learn.example.com/c/course-1?lessonid=lesson-2#outline'
      }
      surface='learner_desktop_header'
      {...overrides}
    />,
  );

describe('CourseShareButton', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    restoreNavigatorProperty('share', originalShare);
    restoreNavigatorProperty('canShare', originalCanShare);
    restoreNavigatorProperty('clipboard', originalClipboard);
  });

  afterAll(() => {
    restoreNavigatorProperty('share', originalShare);
    restoreNavigatorProperty('canShare', originalCanShare);
    restoreNavigatorProperty('clipboard', originalClipboard);
  });

  it('uses native sharing in the click handler and tracks only safe fields', async () => {
    const share = jest.fn().mockResolvedValue(undefined);
    const canShare = jest.fn(() => true);
    setNavigatorProperty('share', share);
    setNavigatorProperty('canShare', canShare);

    renderShareButton();
    fireEvent.click(screen.getByRole('button', { name: 'Share course' }));

    expect(share).toHaveBeenCalledWith({
      title: 'Practical AI',
      text: 'Recommend Practical AI\n\nA hands-on course.',
      url: 'https://learn.example.com/c/course-1',
    });
    await waitFor(() => {
      expect(mockTrackEvent).toHaveBeenCalledTimes(2);
    });
    expect(mockTrackEvent).toHaveBeenNthCalledWith(1, 'course_share_click', {
      shifu_bid: 'course-1',
      surface: 'learner_desktop_header',
    });
    expect(mockTrackEvent).toHaveBeenNthCalledWith(2, 'course_share_result', {
      shifu_bid: 'course-1',
      surface: 'learner_desktop_header',
      method: 'native',
      outcome: 'success',
    });
    expect(mockToast).not.toHaveBeenCalled();
  });

  it('silently tracks a cancelled native share', async () => {
    const abortError = new Error('cancelled');
    abortError.name = 'AbortError';
    setNavigatorProperty('share', jest.fn().mockRejectedValue(abortError));

    renderShareButton({ surface: 'teacher_header' });
    fireEvent.click(screen.getByRole('button', { name: 'Share course' }));

    await waitFor(() => {
      expect(mockTrackEvent).toHaveBeenLastCalledWith('course_share_result', {
        shifu_bid: 'course-1',
        surface: 'teacher_header',
        method: 'native',
        outcome: 'cancelled',
      });
    });
    expect(mockToast).not.toHaveBeenCalled();
  });

  it('copies the complete share message and confirms success', async () => {
    const writeText = jest.fn().mockResolvedValue(undefined);
    setNavigatorProperty('clipboard', { writeText });

    renderShareButton({
      surface: 'learner_mobile_header',
      showLabel: true,
    });
    fireEvent.click(screen.getByRole('button', { name: 'Share course' }));

    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith(
        'Recommend Practical AI\n\nA hands-on course.\n\nhttps://learn.example.com/c/course-1',
      );
    });
    expect(screen.getByText('Share')).toBeInTheDocument();
    expect(mockTrackEvent).toHaveBeenLastCalledWith('course_share_result', {
      shifu_bid: 'course-1',
      surface: 'learner_mobile_header',
      method: 'clipboard',
      outcome: 'success',
    });
    expect(mockToast).toHaveBeenCalledWith({
      title: 'Share content copied',
    });
  });

  it('reports a destructive error after both clipboard strategies fail', async () => {
    setNavigatorProperty('clipboard', {
      writeText: jest.fn().mockRejectedValue(new Error('blocked')),
    });

    renderShareButton({ surface: 'learner_mobile_fullscreen' });
    fireEvent.click(screen.getByRole('button', { name: 'Share course' }));

    await waitFor(() => {
      expect(mockTrackEvent).toHaveBeenLastCalledWith('course_share_result', {
        shifu_bid: 'course-1',
        surface: 'learner_mobile_fullscreen',
        method: 'clipboard',
        outcome: 'failed',
      });
    });
    expect(mockToast).toHaveBeenCalledWith({
      title: 'Unable to share',
      variant: 'destructive',
    });
  });

  it('reports an invalid resolved URL without exposing it to analytics', async () => {
    renderShareButton({
      courseTitle: 'Private course title',
      courseDescription: 'Private course description',
      resolveShareUrl: () => 'javascript:alert(1)',
    });
    fireEvent.click(screen.getByRole('button', { name: 'Share course' }));

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith({
        title: 'Unable to share',
        variant: 'destructive',
      });
    });
    expect(mockTrackEvent.mock.calls).toEqual([
      [
        'course_share_click',
        {
          shifu_bid: 'course-1',
          surface: 'learner_desktop_header',
        },
      ],
      [
        'course_share_result',
        {
          shifu_bid: 'course-1',
          surface: 'learner_desktop_header',
          method: 'clipboard',
          outcome: 'failed',
        },
      ],
    ]);
  });

  it('prevents reentry while sharing is in progress', async () => {
    let finishNativeShare: (() => void) | undefined;
    const share = jest.fn(
      () =>
        new Promise<void>(resolve => {
          finishNativeShare = resolve;
        }),
    );
    setNavigatorProperty('share', share);

    renderShareButton();
    const button = screen.getByRole('button', { name: 'Share course' });
    fireEvent.click(button);
    fireEvent.click(button);

    expect(share).toHaveBeenCalledTimes(1);
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');

    await act(async () => {
      finishNativeShare?.();
    });
    await waitFor(() => expect(button).not.toBeDisabled());
    expect(mockTrackEvent).toHaveBeenCalledTimes(2);
  });

  it('continues sharing when analytics throws synchronously', async () => {
    mockTrackEvent.mockImplementationOnce(() => {
      throw new Error('analytics unavailable');
    });
    const share = jest.fn().mockResolvedValue(undefined);
    setNavigatorProperty('share', share);

    renderShareButton();
    const button = screen.getByRole('button', { name: 'Share course' });
    fireEvent.click(button);

    expect(share).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(button).not.toBeDisabled());
  });
});
