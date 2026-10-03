import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { LessonUpdateNotice } from './LessonUpdateNotice';
const mockReset = jest.fn();
const mockResult = jest.fn();
const mockAllowance = { blocked: false, loading: false, result: mockResult };
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
  mockReset.mockResolvedValue(undefined);
});
it('cannot bypass an exhausted lesson through the update notice', () => {
  mockAllowance.blocked = true;
  render(
    <LessonUpdateNotice
      chapterId='chapter'
      lessonId='lesson'
    />,
  );
  fireEvent.click(screen.getByText('retake'));
  fireEvent.click(screen.getByText('common.core.ok'));
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
