import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { LessonUpdateNotice } from './LessonUpdateNotice';
const mockReset = jest.fn();
const mockResult = jest.fn();
const mockAllowance = {
  blocked: false,
  loading: false,
  failed: false,
  status: {
    available: true,
    allowed: true,
    in_progress: false,
    quota_exempt: false,
  },
  result: mockResult,
};
const mockResetTools = jest.fn();
jest.mock('@/hooks/useRetakeAllowance', () => ({
  useRetakeAllowance: () => mockAllowance,
}));
jest.mock('@/store/useCourseStore', () => ({
  useCourseStore: (fn: (s: object) => unknown) =>
    fn({
      resetChapter: mockReset,
      resettingLessonId: '',
      updateLessonId: jest.fn(),
    }),
}));
jest.mock('@/app/c/[[...id]]/events', () => ({
  stopActiveLessonStream: jest.fn(),
}));
jest.mock('@/lib/shifu/Shifu', () => ({
  shifu: {
    resetTools: {
      resetChapter: (...args: unknown[]) => mockResetTools(...args),
    },
  },
}));
jest.mock('@/hooks/useToast', () => ({ fail: jest.fn() }));
jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
  Trans: ({ components }: { components: { action: React.ReactElement } }) =>
    React.cloneElement(components.action, {}, 'retake'),
}));
jest.mock('@/components/ui/Dialog', () => ({
  Dialog: ({ open, children }: { open: boolean; children: React.ReactNode }) =>
    open ? <div>{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogHeader: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogFooter: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogTitle: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogDescription: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));
beforeEach(() => {
  jest.clearAllMocks();
  mockAllowance.blocked = false;
  mockAllowance.loading = false;
  mockAllowance.failed = false;
  mockAllowance.status = {
    available: true,
    allowed: true,
    in_progress: false,
    quota_exempt: false,
  };
  mockReset.mockResolvedValue(undefined);
});
it('cannot bypass an exhausted lesson through the update notice', () => {
  mockAllowance.blocked = true;
  mockAllowance.status.allowed = false;
  render(
    <LessonUpdateNotice
      chapterId='chapter'
      lessonId='lesson'
    />,
  );
  expect(
    screen.getByText('module.chat.lessonUpdateReviewExisting'),
  ).toBeInTheDocument();
  expect(screen.queryByText('retake')).not.toBeInTheDocument();
  expect(mockReset).not.toHaveBeenCalled();
});
it.each([true, false])(
  'reports the terminal reset outcome: %s',
  async success => {
    if (!success) mockReset.mockRejectedValue(new Error('failure'));
    render(
      <LessonUpdateNotice
        chapterId='chapter'
        lessonId='lesson'
      />,
    );
    fireEvent.click(screen.getByText('retake'));
    fireEvent.click(screen.getByText('common.core.ok'));
    await waitFor(() => expect(mockResult).toHaveBeenCalledWith(success));
    expect(mockReset).toHaveBeenCalledWith('lesson');
    expect(mockResetTools).toHaveBeenCalledTimes(success ? 1 : 0);
  },
);

it.each(['loading', 'failed', 'busy'])(
  'shows a neutral update without an action when %s',
  state => {
    mockAllowance.blocked = true;
    mockAllowance.loading = state === 'loading';
    mockAllowance.failed = state === 'failed';
    mockAllowance.status.allowed = false;
    mockAllowance.status.in_progress = state === 'busy';
    render(
      <LessonUpdateNotice
        chapterId='chapter'
        lessonId='lesson'
      />,
    );
    expect(screen.getByText('module.chat.lessonUpdated')).toBeInTheDocument();
    expect(screen.queryByText('retake')).not.toBeInTheDocument();
    expect(
      screen.queryByText('module.chat.lessonUpdateReviewExisting'),
    ).not.toBeInTheDocument();
  },
);
it('keeps the update action for a quota-exempt owner', () => {
  mockAllowance.status.quota_exempt = true;
  render(
    <LessonUpdateNotice
      chapterId='chapter'
      lessonId='lesson'
    />,
  );
  expect(screen.getByText('retake')).toBeInTheDocument();
});

it('removes reset confirmation copy if quota runs out while the dialog is open', () => {
  const props = { chapterId: 'chapter', lessonId: 'lesson' };
  const { rerender } = render(<LessonUpdateNotice {...props} />);
  fireEvent.click(screen.getByText('retake'));
  expect(
    screen.getByText('module.lesson.reset.confirmContent'),
  ).toBeInTheDocument();
  mockAllowance.blocked = true;
  mockAllowance.status.allowed = false;
  rerender(<LessonUpdateNotice {...props} />);
  expect(
    screen.queryByText('module.lesson.reset.confirmContent'),
  ).not.toBeInTheDocument();
  expect(
    screen.getByText('module.lesson.retake.exhausted'),
  ).toBeInTheDocument();
  expect(screen.getByText('common.core.ok')).toBeDisabled();
  expect(mockReset).not.toHaveBeenCalled();
});
