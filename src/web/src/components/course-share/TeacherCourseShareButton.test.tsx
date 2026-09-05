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
  const guide = screen.queryByRole('button', { name: zh.posterViewPrompt });
  if (guide) fireEvent.click(guide);
};
const clickCopy = () =>
  fireEvent.click(screen.getByRole('button', { name: zh.posterCopy }));

test('prioritizes ordinary sharing and only shows the poster prompt after expansion', () => {
  const view = render(<TeacherCourseShareButton {...props} />);
  fireEvent.click(screen.getByRole('button', { name: zh.shareCourse }));
  expect(
    screen.getByRole('button', { name: zh.shareIntroductionAndLink }),
  ).toBeVisible();
  expect(screen.getByText('https://example.com/c/course-1')).toBeVisible();
  expect(screen.queryByRole('region')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: zh.posterCopy })).toBeVisible();
  expect(screen.getByRole('heading', { name: zh.posterHeading })).toBeVisible();
  expect(screen.getByText(zh.posterHint)).toBeVisible();
  const guide = screen.getByRole('button', { name: zh.posterViewPrompt });
  expect(guide).toHaveAttribute('aria-expanded', 'false');
  fireEvent.click(guide);
  view.rerender(<TeacherCourseShareButton {...props} />);
  expect(screen.getByRole('region')).toBeVisible();
  fireEvent.click(guide);
  expect(screen.queryByRole('region')).not.toBeInTheDocument();
  expect(
    mockTrack.mock.calls.filter(
      ([name]) => name === 'teacher_poster_guide_open',
    ),
  ).toHaveLength(1);
  expect(copy).not.toHaveBeenCalled();
});

test('copies the exact visible prompt, with the full introduction and cleaned link; events contain only allowed fields', async () => {
  const view = render(<TeacherCourseShareButton {...props} />);
  open();
  view.rerender(<TeacherCourseShareButton {...props} />);
  expect(copy).not.toHaveBeenCalled();
  expect(mockTrack).toHaveBeenCalledTimes(2);
  const prompt = screen.getByRole('region', {
    name: zh.posterPromptLabel,
  }).textContent;
  expect(prompt).toContain(description);
  expect(prompt).toContain('https://example.com/c/course-1');
  expect(prompt).not.toContain('secret=value');
  expect(prompt).not.toContain('{courseContent}');
  clickCopy();
  await screen.findByRole('button', { name: zh.posterCopied });
  expect(copy).toHaveBeenCalledWith(prompt);
  expect(mockTrack.mock.calls).toEqual([
    [
      'teacher_course_share_open',
      { shifu_bid: 'course-1', surface: 'teacher_header' },
    ],
    [
      'teacher_poster_guide_open',
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

test('copies the full prompt without expanding its preview', async () => {
  render(<TeacherCourseShareButton {...props} />);
  fireEvent.click(screen.getByRole('button', { name: zh.shareCourse }));
  clickCopy();
  await screen.findByRole('button', { name: zh.posterCopied });
  expect(copy).toHaveBeenCalledWith(expect.stringContaining(description));
  expect(screen.queryByRole('region')).not.toBeInTheDocument();
  expect(mockTrack.mock.calls.map(([name]) => name)).toEqual([
    'teacher_course_share_open',
    'teacher_poster_prompt_copy',
    'teacher_poster_prompt_result',
  ]);
});

test('blocks concurrent copies and preserves manual copy text on failure, then supports retry', async () => {
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
  await act(async () => rejectCopy(new Error('clipboard blocked')));
  expect(screen.getByRole('status')).toHaveTextContent(zh.posterCopyFailed);
  expect(screen.getByRole('region')).toHaveTextContent('最终产出');
  expect(mockTrack).toHaveBeenLastCalledWith('teacher_poster_prompt_result', {
    shifu_bid: 'course-1',
    surface: 'teacher_header',
    outcome: 'failed',
  });
  clickCopy();
  await screen.findByRole('button', { name: zh.posterCopied });
  expect(copy).toHaveBeenCalledTimes(2);
});

test('ordinary sharing still works from the dialog and analytics failure cannot block copying', async () => {
  mockTrack.mockImplementation(() => {
    throw new Error('offline');
  });
  const share = jest.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'share', {
    configurable: true,
    value: share,
  });
  render(<TeacherCourseShareButton {...props} />);
  open();
  fireEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', {
      name: zh.shareIntroductionAndLink,
    }),
  );
  expect(share).toHaveBeenCalledTimes(1);
  clickCopy();
  await screen.findByRole('button', { name: zh.posterCopied });
});

test('invalid URLs cannot produce a prompt or successful exposure event', () => {
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

test('reopening refreshes course content and resets copied state', async () => {
  const view = render(<TeacherCourseShareButton {...props} />);
  open();
  clickCopy();
  await screen.findByRole('button', { name: zh.posterCopied });
  fireEvent.click(
    screen.getByRole('button', { name: 'component.header.close' }),
  );
  await waitFor(() =>
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
  );
  view.rerender(
    <TeacherCourseShareButton
      {...props}
      courseDescription='更新的介绍'
    />,
  );
  open();
  expect(screen.getByRole('region')).toHaveTextContent('更新的介绍');
  expect(screen.getByRole('button', { name: zh.posterCopy })).toBeEnabled();
  expect(
    mockTrack.mock.calls.filter(
      ([event]) => event === 'teacher_course_share_open',
    ),
  ).toHaveLength(2);
});
