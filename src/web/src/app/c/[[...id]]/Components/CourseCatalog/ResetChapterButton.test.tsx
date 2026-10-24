import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { ResetChapterButton } from './ResetChapterButton';

const mockTrackEvent = jest.fn();
const mockResetChapter = jest.fn();
const mockUpdateLessonId = jest.fn();
const mockLegacyResetChapter = jest.fn();
const mockStopActiveLessonStream = jest.fn();

const mockCourseState = {
  resetChapter: mockResetChapter,
  resettingLessonId: '',
  updateLessonId: mockUpdateLessonId,
};
const mockEnvState = { courseId: 'course-1' };
const mockSystemState = { previewMode: false };

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
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

jest.mock('@/lib/shifu/Shifu', () => ({
  shifu: {
    resetTools: {
      resetChapter: (...args: unknown[]) => mockLegacyResetChapter(...args),
    },
  },
}));

jest.mock('@/app/c/[[...id]]/events', () => ({
  stopActiveLessonStream: (...args: unknown[]) =>
    mockStopActiveLessonStream(...args),
}));

jest.mock('@/hooks/useSingleFlight', () => ({
  useSingleFlight: (
    action: (...args: unknown[]) => Promise<unknown> | unknown,
  ) => {
    const ReactModule = jest.requireActual<typeof React>('react');
    const inFlightRef = ReactModule.useRef(false);
    const actionRef = ReactModule.useRef(action);
    actionRef.current = action;
    return ReactModule.useCallback(async (...args: unknown[]) => {
      if (inFlightRef.current) {
        return undefined;
      }
      inFlightRef.current = true;
      try {
        return await actionRef.current(...args);
      } catch {
        return undefined;
      } finally {
        inFlightRef.current = false;
      }
    }, []);
  },
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

const createDeferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });
  return { promise, resolve, reject };
};

const renderResetButton = (onConfirm = jest.fn()) => {
  render(
    <ResetChapterButton
      chapterId='chapter-1'
      chapterName='Private chapter name'
      lessonId='lesson-1'
      onConfirm={onConfirm}
    />,
  );
  return { onConfirm };
};

describe('ResetChapterButton analytics producer', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockCourseState.resettingLessonId = '';
    mockEnvState.courseId = 'course-1';
    mockSystemState.previewMode = false;
  });

  it('deduplicates accepted clicks and in-flight confirms, then tracks success', async () => {
    const reset = createDeferred<void>();
    mockResetChapter.mockReturnValue(reset.promise);
    const { onConfirm } = renderResetButton();

    const resetButton = screen.getByText('module.lesson.reset.title');
    fireEvent.click(resetButton);
    fireEvent.click(resetButton);

    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledWith('reset_chapter', {
      shifu_bid: 'course-1',
      chapter_id: 'chapter-1',
    });

    const confirmButton = screen.getByText('common.core.ok');
    fireEvent.click(confirmButton);
    fireEvent.click(confirmButton);

    expect(mockResetChapter).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);

    await act(async () => {
      reset.resolve();
      await reset.promise;
    });

    await waitFor(() => {
      expect(mockTrackEvent).toHaveBeenLastCalledWith('reset_chapter_confirm', {
        shifu_bid: 'course-1',
        chapter_id: 'chapter-1',
        lesson_id: 'lesson-1',
      });
    });
    expect(mockTrackEvent).toHaveBeenCalledTimes(2);
    expect(mockTrackEvent.mock.calls[1][1]).not.toHaveProperty('chapter_name');
    expect(mockStopActiveLessonStream).toHaveBeenCalledWith('lesson-1');
    expect(mockUpdateLessonId).toHaveBeenCalledWith('lesson-1');
    expect(mockLegacyResetChapter).toHaveBeenCalledWith({
      chapter_id: 'chapter-1',
      lesson_id: 'lesson-1',
      chapter_name: 'Private chapter name',
    });
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('does not emit a confirm event when reset fails', async () => {
    mockResetChapter.mockRejectedValue(new Error('Private API failure'));
    const { onConfirm } = renderResetButton();

    fireEvent.click(screen.getByText('module.lesson.reset.title'));
    fireEvent.click(screen.getByText('common.core.ok'));

    await waitFor(() => expect(mockResetChapter).toHaveBeenCalledTimes(1));
    await act(async () => {
      await Promise.resolve();
    });

    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledWith('reset_chapter', {
      shifu_bid: 'course-1',
      chapter_id: 'chapter-1',
    });
    expect(mockLegacyResetChapter).not.toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('keeps preview resets functional without emitting learner events', async () => {
    mockSystemState.previewMode = true;
    mockResetChapter.mockResolvedValue(undefined);
    const { onConfirm } = renderResetButton();

    fireEvent.click(screen.getByText('module.lesson.reset.title'));
    fireEvent.click(screen.getByText('common.core.ok'));

    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    expect(mockResetChapter).toHaveBeenCalledWith('lesson-1');
    expect(mockTrackEvent).not.toHaveBeenCalled();
  });
});
