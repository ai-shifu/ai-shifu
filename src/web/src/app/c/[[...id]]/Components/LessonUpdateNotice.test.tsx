import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import LessonUpdateNotice from './LessonUpdateNotice';

const mockTrackEvent = jest.fn();
const mockResetChapter = jest.fn();
const mockUpdateLessonId = jest.fn();
const mockResetTools = jest.fn();
const mockStopActiveLessonStream = jest.fn();
const mockFail = jest.fn();
const mockCourseState = {
  resetChapter: mockResetChapter,
  resettingLessonId: '',
  updateLessonId: mockUpdateLessonId,
};
const mockEnvState = { courseId: 'course-1' };
const mockSystemState = { previewMode: false };

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
  Trans: ({ components }: { components: { action: React.ReactElement } }) =>
    components.action,
}));
jest.mock('@/store/useCourseStore', () => ({
  useCourseStore: (selector: (state: typeof mockCourseState) => unknown) =>
    selector(mockCourseState),
}));
jest.mock('@/store/envStore', () => ({
  useEnvStore: (selector: (state: typeof mockEnvState) => unknown) =>
    selector(mockEnvState),
}));
jest.mock('@/store/useSystemStore', () => ({
  useSystemStore: (selector: (state: typeof mockSystemState) => unknown) =>
    selector(mockSystemState),
}));
jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));
jest.mock('@/hooks/useToast', () => ({
  fail: (...args: unknown[]) => mockFail(...args),
}));
jest.mock('@/lib/shifu/Shifu', () => ({
  shifu: {
    resetTools: {
      resetChapter: (...args: unknown[]) => mockResetTools(...args),
    },
  },
}));
jest.mock('@/app/c/[[...id]]/events', () => ({
  stopActiveLessonStream: (...args: unknown[]) =>
    mockStopActiveLessonStream(...args),
}));
jest.mock('@/components/ui/Dialog', () => {
  const ReactModule = jest.requireActual<typeof React>('react');
  const OpenContext = ReactModule.createContext(false);
  const Content = ({ children }: { children: React.ReactNode }) =>
    ReactModule.useContext(OpenContext) ? <div>{children}</div> : null;
  return {
    Dialog: ({
      children,
      open,
    }: {
      children: React.ReactNode;
      open: boolean;
    }) => <OpenContext.Provider value={open}>{children}</OpenContext.Provider>,
    DialogContent: Content,
    DialogDescription: Content,
    DialogFooter: Content,
    DialogHeader: Content,
    DialogTitle: Content,
  };
});

const openConfirm = () =>
  fireEvent.click(
    screen.getByRole('button', {
      name: 'module.chat.lessonUpdateRetakeAccessibleLabel',
    }),
  );

const renderNotice = (lessonId = 'lesson-1') =>
  render(
    <LessonUpdateNotice
      chapterId='chapter-1'
      lessonId={lessonId}
      lessonTitle='Private lesson title'
    />,
  );

describe('recommended lesson retake analytics', () => {
  beforeEach(() => {
    jest.resetAllMocks();
    mockCourseState.resettingLessonId = '';
    mockEnvState.courseId = 'course-1';
    mockSystemState.previewMode = false;
    mockResetChapter.mockResolvedValue(undefined);
  });

  it.each([
    [false, 'published_learning'],
    [true, 'teacher_preview'],
  ])(
    'starts the guarded retake before tracking and reports success for preview %s',
    async (previewMode, surface) => {
      mockSystemState.previewMode = previewMode as boolean;
      let finishReset!: () => void;
      mockResetChapter.mockImplementation(
        () => new Promise<void>(resolve => (finishReset = resolve)),
      );
      renderNotice();
      openConfirm();
      expect(mockTrackEvent).not.toHaveBeenCalled();
      fireEvent.click(screen.getByText('common.core.ok'));
      fireEvent.click(screen.getByText('common.core.ok'));

      expect(mockStopActiveLessonStream).toHaveBeenCalledTimes(1);
      expect(mockResetChapter).toHaveBeenCalledTimes(1);
      expect(mockTrackEvent).not.toHaveBeenCalled();
      await act(async () => {
        await Promise.resolve();
      });

      const payload = {
        shifu_bid: 'course-1',
        outline_bid: 'lesson-1',
        surface,
      };
      expect(mockTrackEvent.mock.calls).toEqual([
        ['lesson_update_retake_attempt', payload],
      ]);
      expect(mockResetChapter.mock.invocationCallOrder[0]).toBeLessThan(
        mockTrackEvent.mock.invocationCallOrder[0],
      );
      expect(
        mockStopActiveLessonStream.mock.invocationCallOrder[0],
      ).toBeLessThan(mockResetChapter.mock.invocationCallOrder[0]);

      await act(async () => finishReset());
      await waitFor(() => {
        expect(screen.queryByText('common.core.ok')).not.toBeInTheDocument();
      });
      expect(mockTrackEvent.mock.calls).toEqual([
        ['lesson_update_retake_attempt', payload],
        ['lesson_update_retake_result', { ...payload, outcome: 'success' }],
      ]);
      expect(mockUpdateLessonId).toHaveBeenCalledWith('lesson-1');
      expect(mockResetTools).toHaveBeenCalledWith({
        chapter_id: 'chapter-1',
        lesson_id: 'lesson-1',
        chapter_name: 'Private lesson title',
      });
      for (const [, data] of mockTrackEvent.mock.calls) {
        expect(data).not.toHaveProperty('chapter_name');
        expect(data).not.toHaveProperty('lessonTitle');
        expect(data).not.toHaveProperty('content');
        expect(data).not.toHaveProperty('error');
      }
    },
  );

  it('tracks a terminal failure and permits a later deliberate retry', async () => {
    mockResetChapter.mockRejectedValueOnce(new Error('Private API failure'));
    renderNotice();
    openConfirm();
    fireEvent.click(screen.getByText('common.core.ok'));
    await waitFor(() => expect(mockFail).toHaveBeenCalledTimes(1));
    expect(mockTrackEvent.mock.calls).toEqual([
      [
        'lesson_update_retake_attempt',
        {
          shifu_bid: 'course-1',
          outline_bid: 'lesson-1',
          surface: 'published_learning',
        },
      ],
      [
        'lesson_update_retake_result',
        {
          shifu_bid: 'course-1',
          outline_bid: 'lesson-1',
          surface: 'published_learning',
          outcome: 'failed',
        },
      ],
    ]);
    expect(mockResetTools).not.toHaveBeenCalled();
    expect(screen.getByText('common.core.ok')).toBeInTheDocument();

    fireEvent.click(screen.getByText('common.core.ok'));
    await waitFor(() => expect(mockResetTools).toHaveBeenCalledTimes(1));
    expect(mockTrackEvent).toHaveBeenCalledTimes(4);
    expect(mockTrackEvent.mock.calls[3][1].outcome).toBe('success');
  });

  it('does not start a retake or analytics when confirmation is cancelled', () => {
    renderNotice();
    openConfirm();
    fireEvent.click(screen.getByText('common.core.cancel'));
    expect(screen.queryByText('common.core.ok')).not.toBeInTheDocument();
    expect(mockTrackEvent).not.toHaveBeenCalled();
    expect(mockResetChapter).not.toHaveBeenCalled();
  });

  it.each(['lesson', 'pending'])(
    'excludes invalid or disabled %s state',
    state => {
      if (state === 'pending') mockCourseState.resettingLessonId = 'lesson-1';
      renderNotice(state === 'lesson' ? '' : 'lesson-1');
      openConfirm();
      expect(screen.queryByText('common.core.ok')).not.toBeInTheDocument();
      expect(mockTrackEvent).not.toHaveBeenCalled();
      expect(mockResetChapter).not.toHaveBeenCalled();
    },
  );

  it.each([
    [false, false],
    [true, false],
    [false, true],
    [true, true],
  ])(
    'retakes without analytics course metadata in preview %s with reset failure %s',
    async (previewMode, resetFails) => {
      mockEnvState.courseId = '';
      mockSystemState.previewMode = previewMode;
      let finishReset!: () => void;
      mockResetChapter.mockImplementation(
        () =>
          new Promise<void>((resolve, reject) => {
            finishReset = () =>
              resetFails ? reject(new Error('Reset failed')) : resolve();
          }),
      );
      renderNotice();
      openConfirm();
      fireEvent.click(screen.getByText('common.core.ok'));
      fireEvent.click(screen.getByText('common.core.ok'));
      expect(mockResetChapter).toHaveBeenCalledTimes(1);
      expect(mockResetChapter).toHaveBeenCalledWith('lesson-1');
      expect(mockStopActiveLessonStream).toHaveBeenCalledTimes(1);
      expect(mockStopActiveLessonStream).toHaveBeenCalledWith('lesson-1');
      expect(mockTrackEvent).not.toHaveBeenCalled();

      await act(async () => finishReset());
      if (resetFails) {
        expect(mockFail).toHaveBeenCalledWith('Reset failed');
        expect(mockUpdateLessonId).not.toHaveBeenCalled();
        expect(mockResetTools).not.toHaveBeenCalled();
        expect(screen.getByText('common.core.ok')).toBeInTheDocument();
      } else {
        expect(mockFail).not.toHaveBeenCalled();
        expect(mockUpdateLessonId).toHaveBeenCalledWith('lesson-1');
        expect(mockResetTools).toHaveBeenCalledTimes(1);
        expect(screen.queryByText('common.core.ok')).not.toBeInTheDocument();
      }
      expect(mockTrackEvent).not.toHaveBeenCalled();
    },
  );

  it.each(['throw', 'reject', 'pending'])(
    'completes the retake when tracking is %s',
    async failure => {
      mockTrackEvent.mockImplementation(() => {
        if (failure === 'throw') throw new Error('Tracking unavailable');
        if (failure === 'reject')
          return Promise.reject(new Error('Tracking unavailable'));
        return new Promise<void>(() => {});
      });
      renderNotice();
      openConfirm();
      fireEvent.click(screen.getByText('common.core.ok'));
      await waitFor(() => expect(mockResetTools).toHaveBeenCalledTimes(1));
      expect(screen.queryByText('common.core.ok')).not.toBeInTheDocument();
      expect(mockFail).not.toHaveBeenCalled();
      expect(mockTrackEvent).toHaveBeenCalledTimes(2);
    },
  );
});
