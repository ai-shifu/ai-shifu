import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { TeacherCourseShareButton } from './TeacherCourseShareButton';
import zh from '../../../../i18n/zh-CN/common/core.json';

const mockTrack = jest.fn();
const mockToast = jest.fn();
jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrack }),
}));
jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
}));
jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values: Record<string, string> = {}) => {
      const messages = jest.requireActual(
        '../../../../i18n/zh-CN/common/core.json',
      );
      const template = messages[key.replace('common.core.', '')] || key;
      return template.replace(
        /\{(\w+)\}/g,
        (_: string, field: string) => values[field] ?? `{${field}}`,
      );
    },
  }),
}));

const description =
  '第一段：业务定位。\n\n' +
  '完整的课程介绍。'.repeat(90) +
  '\n最终产出：方向图，而非交付包。';
const props = {
  courseTitle: 'AI 业务操盘手',
  courseDescription: description,
  shifuBid: 'course-1',
  resolveShareUrl: () => 'https://example.com/c/course-1?secret=value#outline',
  surface: 'teacher_header' as const,
  showLabel: true,
};
const clipboardDescriptor = Object.getOwnPropertyDescriptor(
  navigator,
  'clipboard',
);
const shareDescriptor = Object.getOwnPropertyDescriptor(navigator, 'share');
const copy = jest.fn();
beforeEach(() => {
  jest.clearAllMocks();
  mockTrack.mockReset();
  copy.mockReset();
  copy.mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText: copy },
  });
});
afterAll(() => {
  for (const [key, descriptor] of [
    ['clipboard', clipboardDescriptor],
    ['share', shareDescriptor],
  ] as const) {
    if (descriptor) Object.defineProperty(navigator, key, descriptor);
    else delete (navigator as unknown as Record<string, unknown>)[key];
  }
});
const open = () => {
  fireEvent.click(screen.getByRole('button', { name: zh.shareCourse }));
};
const clickCopy = () =>
  fireEvent.click(screen.getByRole('button', { name: zh.posterCopy }));
const closed = () =>
  waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

test('shows only two actions in a non-modal anchored popover', () => {
  render(<TeacherCourseShareButton {...props} />);
  open();
  const popup = screen.getByRole('dialog');
  expect(within(popup).getAllByRole('button')).toHaveLength(2);
  expect(
    within(popup).getByRole('button', { name: zh.shareCourse }),
  ).toBeVisible();
  expect(screen.getByRole('button', { name: zh.posterCopy })).toBeVisible();
  expect(screen.queryByText(props.courseTitle)).not.toBeInTheDocument();
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  expect(document.body).not.toHaveStyle({ pointerEvents: 'none' });
  expect(copy).not.toHaveBeenCalled();
});

test('copies complete course prompt and closes with a next-step toast and privacy-safe events', async () => {
  const view = render(<TeacherCourseShareButton {...props} />);
  open();
  view.rerender(<TeacherCourseShareButton {...props} />);
  expect(mockTrack).toHaveBeenCalledTimes(1);
  clickCopy();
  await closed();
  expect(copy).toHaveBeenCalledWith(expect.stringContaining(description));
  const prompt = copy.mock.calls[0][0];
  expect(prompt).toContain('https://example.com/c/course-1');
  expect(prompt).not.toContain('secret=value');
  expect(prompt).not.toContain('{courseContent}');
  expect(mockToast).toHaveBeenCalledWith({ title: zh.posterNextStep });
  expect(mockTrack.mock.calls).toEqual([
    [
      'teacher_course_share_open',
      { shifu_bid: 'course-1', surface: 'teacher_header' },
    ],
    [
      'teacher_poster_prompt_copy',
      { shifu_bid: 'course-1', surface: 'teacher_header' },
    ],
    [
      'teacher_poster_prompt_result',
      { shifu_bid: 'course-1', surface: 'teacher_header', outcome: 'success' },
    ],
  ]);
});

test('blocks concurrent copies and keeps manual fallback on failure then retries', async () => {
  let rejectCopy: (reason: Error) => void = () => {};
  copy.mockImplementationOnce(
    () =>
      new Promise((_, reject) => {
        rejectCopy = reject;
      }),
  );

  render(<TeacherCourseShareButton {...props} />);
  open();
  clickCopy();
  clickCopy();
  expect(copy).toHaveBeenCalledTimes(1);
  await act(async () => rejectCopy(new Error('blocked')));
  expect(screen.getByRole('textbox')).toHaveValue(copy.mock.calls[0][0]);
  expect(mockToast).toHaveBeenCalledWith({
    title: zh.posterCopyFailed,
    variant: 'destructive',
  });
  expect(mockTrack).toHaveBeenLastCalledWith('teacher_poster_prompt_result', {
    shifu_bid: 'course-1',
    surface: 'teacher_header',
    outcome: 'failed',
  });
  clickCopy();
  await closed();
  expect(copy).toHaveBeenCalledTimes(2);
});

test.each(['success', 'cancelled'])(
  'native sharing closes after %s even when analytics fails',
  async outcome => {
    mockTrack.mockImplementation(() => {
      throw new Error('offline');
    });
    const share =
      outcome === 'success'
        ? jest.fn().mockResolvedValue(undefined)
        : jest
            .fn()
            .mockRejectedValue(new DOMException('cancelled', 'AbortError'));
    Object.defineProperty(navigator, 'share', {
      configurable: true,
      value: share,
    });
    render(<TeacherCourseShareButton {...props} />);
    open();
    fireEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: zh.shareCourse,
      }),
    );
    expect(share).toHaveBeenCalledTimes(1);
    await closed();
  },
);

test('copying still works when tracking rejects', async () => {
  mockTrack.mockRejectedValue(new Error('offline'));
  render(<TeacherCourseShareButton {...props} />);
  open();
  clickCopy();
  await closed();
  expect(copy).toHaveBeenCalledTimes(1);
});

test('ordinary share failure closes with existing error feedback', async () => {
  Object.defineProperty(navigator, 'share', {
    configurable: true,
    value: undefined,
  });
  copy.mockRejectedValue(new Error('blocked'));
  render(<TeacherCourseShareButton {...props} />);
  open();
  fireEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', {
      name: zh.shareCourse,
    }),
  );
  await closed();
  expect(mockToast).toHaveBeenCalledWith({
    title: zh.shareFailed,
    variant: 'destructive',
  });
});

test('pending sharing blocks prompt copying and reopening until completion', async () => {
  let finish: () => void = () => {};
  Object.defineProperty(navigator, 'share', {
    configurable: true,
    value: jest.fn(
      () =>
        new Promise<void>(resolve => {
          finish = resolve;
        }),
    ),
  });
  render(<TeacherCourseShareButton {...props} />);
  open();
  fireEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', {
      name: zh.shareCourse,
    }),
  );
  expect(screen.getByRole('button', { name: zh.posterCopy })).toBeDisabled();
  fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
  await closed();
  open();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  await act(async () => finish());
  open();
  expect(screen.getByRole('button', { name: zh.posterCopy })).toBeEnabled();
});

test('invalid URLs cannot produce a prompt or exposure event', () => {
  render(
    <TeacherCourseShareButton
      {...props}
      resolveShareUrl={() => 'javascript:alert(1)'}
    />,
  );
  open();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(mockTrack).not.toHaveBeenCalled();
  expect(copy).not.toHaveBeenCalled();
});

test('reopening refreshes the current course data', async () => {
  const view = render(<TeacherCourseShareButton {...props} />);
  open();
  clickCopy();
  await closed();
  view.rerender(
    <TeacherCourseShareButton
      {...props}
      courseDescription='更新的介绍'
    />,
  );
  open();
  clickCopy();
  await closed();
  expect(copy.mock.calls[1][0]).toContain('更新的介绍');
  expect(copy.mock.calls[1][0]).not.toContain(description);
  expect(
    mockTrack.mock.calls.filter(
      ([event]) => event === 'teacher_course_share_open',
    ),
  ).toHaveLength(2);
});

test('Escape closes and restores focus without copying', async () => {
  render(<TeacherCourseShareButton {...props} />);
  const trigger = screen.getByRole('button', { name: zh.shareCourse });
  open();
  fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
  await closed();
  expect(trigger).toHaveFocus();
  expect(copy).not.toHaveBeenCalled();
});

test('outside interaction dismisses without copying', async () => {
  render(
    <>
      <button>{zh.share}</button>
      <TeacherCourseShareButton {...props} />
    </>,
  );
  open();
  // Radix installs its outside pointer listener on the next task.
  await act(async () => {
    await new Promise(resolve => setTimeout(resolve, 0));
  });
  fireEvent.pointerDown(
    screen.getByRole('button', { name: zh.share, exact: true }),
    {
      pointerType: 'mouse',
    },
  );
  fireEvent.focusIn(
    screen.getByRole('button', { name: zh.share, exact: true }),
  );
  await closed();
  expect(copy).not.toHaveBeenCalled();
});

const pointer = (element: Element, type: string, pointerType: string) => {
  const event = new Event(type, { bubbles: true });
  Object.defineProperty(event, 'pointerType', { value: pointerType });
  fireEvent(element, event);
};

test('mouse departure dismisses after a grace period and re-entry cancels dismissal', () => {
  jest.useFakeTimers();
  try {
    render(<TeacherCourseShareButton {...props} />);
    open();
    const popup = screen.getByRole('dialog');
    pointer(popup, 'pointerout', 'mouse');
    act(() => jest.advanceTimersByTime(150));
    expect(popup).toBeVisible();
    pointer(popup, 'pointerover', 'mouse');
    act(() => jest.advanceTimersByTime(300));
    expect(popup).toBeVisible();
    pointer(popup, 'pointerout', 'mouse');
    act(() => jest.advanceTimersByTime(301));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(copy).not.toHaveBeenCalled();
  } finally {
    jest.useRealTimers();
  }
});

test('touch departure does not dismiss the choices', () => {
  jest.useFakeTimers();
  try {
    render(<TeacherCourseShareButton {...props} />);
    open();
    pointer(screen.getByRole('dialog'), 'pointerout', 'touch');
    act(() => jest.advanceTimersByTime(1000));
    expect(screen.getByRole('dialog')).toBeVisible();
  } finally {
    jest.useRealTimers();
  }
});
