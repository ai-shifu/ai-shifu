import { act, renderHook } from '@testing-library/react';
import { getLessonTree } from '@/api/lesson';
import { useLessonTree } from './use-lesson-tree';

let mockPreviewMode = false;
jest.mock('@/api/lesson', () => ({ getLessonTree: jest.fn() }));
jest.mock('@/api/learning', () => ({
  LEARNING_PERMISSION: {
    NORMAL: 'normal',
    TRIAL: 'trial',
    GUEST: 'guest',
  },
}));
jest.mock('@/hooks/use-tracking', () => ({
  useTracking: () => ({ trackEvent: jest.fn() }),
}));
jest.mock('@/store/env-store', () => ({
  useEnvStore: { getState: () => ({ courseId: 'guide-course' }) },
}));
jest.mock('@/store/use-system-store', () => ({
  useSystemStore: (selector: (state: { previewMode: boolean }) => unknown) =>
    selector({ previewMode: mockPreviewMode }),
}));
jest.mock('@/store', () => ({
  useUserStore: (selector: (state: { isLoggedIn: boolean }) => unknown) =>
    selector({ isLoggedIn: true }),
}));
jest.mock('@/store/use-course-store', () => ({
  useCourseStore: (selector: (state: { openPayModal: jest.Mock }) => unknown) =>
    selector({ openPayModal: jest.fn() }),
}));

const mockGetLessonTree = getLessonTree as jest.Mock;

describe('useLessonTree authored language metadata', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockPreviewMode = false;
  });

  it('keeps the authored guide title language across tree reloads', async () => {
    mockGetLessonTree.mockResolvedValueOnce({
      outline_items: [],
      title_language: 'en-US',
      content_language: 'en-US',
    });
    mockGetLessonTree.mockResolvedValueOnce({
      outline_items: [],
      title_language: 'zh-CN',
      content_language: 'zh-CN',
    });

    const { result } = renderHook(() => useLessonTree());
    await act(async () => {
      await result.current.loadTree();
    });
    expect(result.current.tree?.titleLanguage).toBe('en-US');
    expect(result.current.tree?.contentLanguage).toBe('en-US');

    await act(async () => {
      await result.current.reloadTree();
    });
    expect(result.current.tree?.titleLanguage).toBe('zh-CN');
    expect(result.current.tree?.contentLanguage).toBe('zh-CN');
    expect(mockGetLessonTree).toHaveBeenCalledWith('guide-course', false);
  });

  it('loads a draft-only course by its route ID and draft selector', async () => {
    mockPreviewMode = true;
    mockGetLessonTree.mockResolvedValueOnce({ outline_items: [] });
    const { result } = renderHook(() => useLessonTree('draft-only-course'));

    await act(async () => {
      await result.current.loadTree();
    });

    expect(mockGetLessonTree.mock.calls).toEqual([['draft-only-course', true]]);
  });

  it('leaves ordinary courses without a content language override', async () => {
    mockGetLessonTree.mockResolvedValue({ outline_items: [] });

    const { result } = renderHook(() => useLessonTree());
    await act(async () => {
      await result.current.loadTree();
    });

    expect(result.current.tree?.titleLanguage).toBeUndefined();
    expect(result.current.tree?.contentLanguage).toBeUndefined();
  });
});

describe('useLessonTree reload with streamed and recovered progress', () => {
  const outline = (status: string) => ({
    outline_items: [
      {
        bid: 'chapter-1',
        title: 'Chapter',
        status: 'in_progress',
        type: 'guest',
        is_paid: true,
        children: [
          {
            bid: 'lesson-1',
            title: 'Current lesson',
            status,
            type: 'guest',
            is_paid: true,
          },
          {
            bid: 'lesson-2',
            title: 'Next lesson',
            status: 'not_started',
            type: 'guest',
            is_paid: true,
          },
        ],
      },
    ],
  });

  beforeEach(() => {
    mockGetLessonTree.mockReset();
    mockPreviewMode = false;
  });

  it('keeps lesson and chapter patches that arrived after a reload started', async () => {
    let finishReload!: (value: ReturnType<typeof outline>) => void;
    mockGetLessonTree.mockResolvedValueOnce(outline('in_progress'));
    mockGetLessonTree.mockReturnValueOnce(
      new Promise(resolve => {
        finishReload = resolve;
      }),
    );
    const { result } = renderHook(() => useLessonTree('course-1'));
    await act(async () => {
      await result.current.loadTree('chapter-1', 'lesson-1');
    });

    let reload!: ReturnType<typeof result.current.reloadTree>;
    act(() => {
      reload = result.current.reloadTree('chapter-1', 'lesson-1');
    });
    act(() => {
      result.current.updateLesson('lesson-1', {
        name: 'Updated title',
        status: 'completed',
        status_value: 'completed',
      });
      result.current.updateChapterStatus('chapter-1', {
        status: 'completed',
        status_value: 'completed',
      });
      result.current.updateLesson('lesson-2', {
        status: 'in_progress',
        status_value: 'in_progress',
      });
      result.current.toggleCollapse({ id: 'chapter-1' });
    });
    expect(result.current.tree?.catalogs[0].lessons[1].status).toBe(
      'in_progress',
    );
    await act(async () => {
      finishReload(outline('in_progress'));
      await reload;
    });

    expect(result.current.selectedLessonId).toBe('lesson-1');
    expect(result.current.tree?.catalogs[0]).toMatchObject({
      collapse: true,
      status: 'completed',
      lessons: [
        { id: 'lesson-1', name: 'Updated title', status: 'completed' },
        { id: 'lesson-2', status: 'in_progress', canLearning: true },
      ],
    });
    expect(mockGetLessonTree).toHaveBeenCalledTimes(2);
  });

  it('keeps a completed retake when the server returns it after reset retry', async () => {
    mockGetLessonTree.mockResolvedValue(outline('completed'));
    const { result } = renderHook(() => useLessonTree('course-1'));
    await act(async () => {
      await result.current.reloadTree('chapter-1', 'lesson-1');
    });
    expect(result.current.selectedLessonId).toBe('lesson-1');
    expect(result.current.tree?.catalogs[0].lessons[0]).toMatchObject({
      status: 'completed',
      status_value: 'completed',
      canLearning: true,
    });
  });

  it('rejects an older catalog response before it can select another lesson', async () => {
    let finishOlder!: (value: ReturnType<typeof outline>) => void;
    mockGetLessonTree.mockReturnValueOnce(
      new Promise(resolve => {
        finishOlder = resolve;
      }),
    );
    mockGetLessonTree.mockResolvedValueOnce(outline('completed'));
    const { result } = renderHook(() => useLessonTree('course-1'));

    let older!: ReturnType<typeof result.current.reloadTree>;
    act(() => {
      older = result.current.reloadTree('chapter-1', 'lesson-2');
    });
    await act(async () => {
      await result.current.reloadTree('chapter-1', 'lesson-1');
    });
    await act(async () => {
      finishOlder(outline('in_progress'));
      expect(await older).toBeUndefined();
    });

    expect(result.current.selectedLessonId).toBe('lesson-1');
    expect(result.current.tree?.catalogs[0].lessons[0].status).toBe(
      'completed',
    );
  });

  it.each(['empty response', 'rejection'])(
    'keeps a loaded catalog and selected lesson on refresh %s',
    async failure => {
      let finishReload!: (value: null) => void;
      let failReload!: (error: Error) => void;
      mockGetLessonTree.mockResolvedValueOnce(outline('in_progress'));
      mockGetLessonTree.mockReturnValueOnce(
        new Promise((resolve, reject) => {
          finishReload = resolve;
          failReload = reject;
        }),
      );
      const { result } = renderHook(() => useLessonTree('course-1'));
      await act(async () => {
        await result.current.loadTree('chapter-1', 'lesson-2');
      });
      const previousTree = result.current.tree;

      let reload!: ReturnType<typeof result.current.reloadTree>;
      act(() => {
        reload = result.current.reloadTree();
      });
      const settled = reload.catch(error => error);
      await act(async () => {
        if (failure === 'rejection') {
          failReload(new Error('Request failed'));
          expect(await settled).toEqual(new Error('Request failed'));
        } else {
          finishReload(null);
          expect(await settled).toBeNull();
        }
      });

      expect(result.current.tree).toBe(previousTree);
      expect(result.current.selectedLessonId).toBe('lesson-2');
    },
  );

  it.each(['cached route', 'catalog click'])(
    'keeps a newer lesson selected after a reload started (%s)',
    async source => {
      type Outline = ReturnType<typeof outline> & { title_language?: string };
      let finishReload!: (value: Outline) => void;
      mockGetLessonTree.mockResolvedValueOnce(outline('in_progress'));
      mockGetLessonTree.mockReturnValueOnce(
        new Promise(resolve => {
          finishReload = resolve;
        }),
      );
      const { result } = renderHook(() => useLessonTree('course-1'));
      await act(async () => {
        await result.current.loadTree('chapter-1', 'lesson-1');
      });

      let reload!: ReturnType<typeof result.current.reloadTree>;
      act(() => {
        reload =
          source === 'cached route'
            ? result.current.reloadTree()
            : result.current.reloadTree('chapter-1', 'lesson-1');
      });
      await act(async () => {
        if (source === 'cached route') {
          await result.current.loadTree('chapter-1', 'lesson-2');
        } else {
          await result.current.updateSelectedLesson('lesson-2');
        }
      });
      await act(async () => {
        finishReload({ ...outline('in_progress'), title_language: 'fr-FR' });
        await reload;
      });

      expect(result.current.selectedLessonId).toBe('lesson-2');
      expect(result.current.tree?.titleLanguage).toBe('fr-FR');
      expect(await reload).toBeUndefined();
      expect(mockGetLessonTree).toHaveBeenCalledTimes(2);
    },
  );

  it('discards an outstanding response when its course scope changes', async () => {
    let finishFirst!: (value: ReturnType<typeof outline>) => void;
    mockGetLessonTree
      .mockReturnValueOnce(
        new Promise(resolve => {
          finishFirst = resolve;
        }),
      )
      .mockResolvedValueOnce(outline('completed'));
    const { result, rerender } = renderHook(
      ({ courseId }) => useLessonTree(courseId),
      { initialProps: { courseId: 'course-1' } },
    );

    let first!: ReturnType<typeof result.current.loadTree>;
    act(() => {
      first = result.current.loadTree('chapter-1', 'lesson-2');
    });
    rerender({ courseId: 'course-2' });
    await act(async () => {
      finishFirst(outline('in_progress'));
      expect(await first).toBeUndefined();
    });

    expect(result.current.selectedLessonId).toBeNull();
    await act(async () => {
      await result.current.loadTree('chapter-1', 'lesson-1');
    });
    expect(result.current.selectedLessonId).toBe('lesson-1');
    expect(mockGetLessonTree.mock.calls).toEqual([
      ['course-1', false],
      ['course-2', false],
    ]);
  });
  it('refreshes unknown successors once without changing the current lesson', async () => {
    let finishRefresh!: (value: ReturnType<typeof outline>) => void;
    mockGetLessonTree.mockResolvedValueOnce(outline('completed'));
    mockGetLessonTree.mockReturnValueOnce(
      new Promise(resolve => {
        finishRefresh = resolve;
      }),
    );
    const { result } = renderHook(() => useLessonTree('course-1'));
    await act(async () => {
      await result.current.loadTree('chapter-1', 'lesson-1');
    });
    act(() => {
      result.current.toggleCollapse({ id: 'chapter-1' });
      result.current.updateChapterStatus('nested-chapter', {
        status: 'completed',
        status_value: 'completed',
      });
      result.current.updateLesson('unknown-stream-lesson', {
        status: 'in_progress',
      });
      expect(mockGetLessonTree).toHaveBeenCalledTimes(1);
      result.current.updateLesson(
        'lesson-new',
        {
          status: 'in_progress',
          status_value: 'in_progress',
        },
        { refreshMissingLesson: true },
      );
      result.current.updateChapterStatus('chapter-1', {
        status: 'completed',
        status_value: 'completed',
      });
      result.current.updateLesson('lesson-new', {
        status: 'completed',
        status_value: 'completed',
      });
    });

    expect(result.current.selectedLessonId).toBe('lesson-1');
    expect(mockGetLessonTree).toHaveBeenCalledTimes(2);
    expect(mockGetLessonTree).toHaveBeenLastCalledWith('course-1', false, {
      skipErrorToast: true,
    });

    const refreshedOutline = outline('completed');
    refreshedOutline.outline_items[0].children.splice(1, 0, {
      bid: 'lesson-new',
      title: 'New successor',
      status: 'not_started',
      type: 'guest',
      is_paid: true,
    });
    await act(async () => finishRefresh(refreshedOutline));

    expect(result.current.selectedLessonId).toBe('lesson-1');
    expect(result.current.getNextLessonId()).toBe('lesson-new');
    expect(result.current.tree?.catalogs[0]).toMatchObject({
      collapse: true,
      status: 'completed',
      lessons: [
        { id: 'lesson-1', status: 'completed' },
        { id: 'lesson-new', status: 'completed', canLearning: true },
        { id: 'lesson-2', status: 'not_started' },
      ],
    });
    expect(mockGetLessonTree).toHaveBeenCalledTimes(2);
  });

  it('checks a missing target after a foreground reload without looping', async () => {
    let finishReload!: (value: ReturnType<typeof outline>) => void;
    mockGetLessonTree
      .mockResolvedValueOnce(outline('completed'))
      .mockReturnValueOnce(
        new Promise(resolve => {
          finishReload = resolve;
        }),
      )
      .mockResolvedValueOnce(outline('completed'));
    const { result } = renderHook(() => useLessonTree('course-1'));
    await act(async () => {
      await result.current.loadTree('chapter-1', 'lesson-1');
    });

    let reload!: ReturnType<typeof result.current.reloadTree>;
    act(() => {
      reload = result.current.reloadTree('chapter-1', 'lesson-1');
      result.current.updateLesson(
        'lesson-unknown',
        {
          status: 'in_progress',
        },
        { refreshMissingLesson: true },
      );
    });
    expect(mockGetLessonTree).toHaveBeenCalledTimes(2);
    await act(async () => {
      finishReload(outline('completed'));
      await reload;
    });

    expect(result.current.selectedLessonId).toBe('lesson-1');
    expect(result.current.getNextLessonId()).toBe('lesson-2');
    expect(mockGetLessonTree).toHaveBeenCalledTimes(3);
  });

  it('keeps the reset selection when an older structure refresh returns', async () => {
    let finishRefresh!: (value: ReturnType<typeof outline>) => void;
    mockGetLessonTree
      .mockResolvedValueOnce(outline('in_progress'))
      .mockReturnValueOnce(
        new Promise(resolve => {
          finishRefresh = resolve;
        }),
      )
      .mockResolvedValueOnce(outline('completed'));
    const { result } = renderHook(() => useLessonTree('course-1'));
    await act(async () => {
      await result.current.loadTree('chapter-1', 'lesson-1');
    });
    act(() =>
      result.current.updateLesson(
        'lesson-unknown',
        { status: 'in_progress' },
        { refreshMissingLesson: true },
      ),
    );
    expect(mockGetLessonTree).toHaveBeenCalledTimes(2);
    await act(async () => {
      await result.current.reloadTree('chapter-1', 'lesson-2');
    });
    await act(async () => finishRefresh(outline('in_progress')));

    expect(result.current.selectedLessonId).toBe('lesson-2');
    expect(result.current.tree?.catalogs[0].lessons[0].status).toBe(
      'completed',
    );
    expect(mockGetLessonTree).toHaveBeenCalledTimes(3);
  });
});
