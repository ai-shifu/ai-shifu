import React from 'react';
import type { LearningPermission } from '@/api/studyV2';
import { act, renderHook, waitFor } from '@testing-library/react';

const mockSaveMdflow = jest.fn();
const mockGetShifuDraftMeta = jest.fn();
const mockGetShifuDetail = jest.fn();
const mockCreateOutline = jest.fn();
const mockGetProfileItemDefinitions = jest.fn();
const mockGetProfileVariableUsage = jest.fn();
const mockTrackEvent = jest.fn();

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    saveMdflow: (...args: unknown[]) => mockSaveMdflow(...args),
    getShifuDraftMeta: (...args: unknown[]) => mockGetShifuDraftMeta(...args),
    getShifuDetail: (...args: unknown[]) => mockGetShifuDetail(...args),
    createOutline: (...args: unknown[]) => mockCreateOutline(...args),
    getProfileItemDefinitions: (...args: unknown[]) =>
      mockGetProfileItemDefinitions(...args),
    getProfileVariableUsage: (...args: unknown[]) =>
      mockGetProfileVariableUsage(...args),
  },
}));

jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({
    trackEvent: mockTrackEvent,
  }),
}));

jest.mock('@/lib/browser-timezone', () => ({
  getBrowserTimeZone: jest.fn(() => 'Asia/Shanghai'),
}));

jest.mock('@/api/studyV2', () => ({
  LEARNING_PERMISSION: {
    GUEST: 'guest',
    TRIAL: 'trial',
  },
}));

import { ShifuProvider, useShifu } from './useShifu';

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <ShifuProvider>{children}</ShifuProvider>
);

const createDeferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });
  return { promise, resolve, reject };
};

describe('useShifu draft meta handling', () => {
  beforeEach(() => {
    mockSaveMdflow.mockReset();
    mockGetShifuDraftMeta.mockReset();
    mockGetShifuDetail.mockReset();
    mockCreateOutline.mockReset();
    mockTrackEvent.mockReset();
  });

  it('loads draft meta without browser timezone', async () => {
    mockGetShifuDraftMeta.mockResolvedValue({
      revision: 2,
      updated_at: '2026-06-30T05:37:42Z',
      updated_user: null,
    });

    const { result } = renderHook(() => useShifu(), { wrapper });

    await act(async () => {
      result.current.actions.setCurrentNode({
        bid: 'lesson-1',
        depth: 1,
      } as any);
      await result.current.actions.loadDraftMeta('shifu-1', 'lesson-1');
    });

    expect(mockGetShifuDraftMeta).toHaveBeenCalledWith({
      shifu_bid: 'shifu-1',
      outline_bid: 'lesson-1',
    });
    expect(result.current.latestDraftMeta?.updated_at).toBe(
      '2026-06-30T05:37:42Z',
    );
  });

  it('refreshes draft meta after saving mdflow successfully', async () => {
    mockSaveMdflow.mockResolvedValue({ new_revision: 9 });
    mockGetShifuDraftMeta.mockResolvedValue({
      revision: 9,
      updated_at: '2026-06-30T05:37:42Z',
      updated_user: null,
    });

    const { result } = renderHook(() => useShifu(), { wrapper });

    await act(async () => {
      result.current.actions.setCurrentNode({
        bid: 'lesson-1',
        depth: 1,
      } as any);
      await result.current.actions.saveMdflow({
        shifu_bid: 'shifu-1',
        outline_bid: 'lesson-1',
        data: 'updated content',
      });
    });

    expect(mockSaveMdflow).toHaveBeenCalledWith({
      shifu_bid: 'shifu-1',
      outline_bid: 'lesson-1',
      data: 'updated content',
      base_revision: undefined,
    });
    await waitFor(() => {
      expect(mockGetShifuDraftMeta).toHaveBeenCalledWith({
        shifu_bid: 'shifu-1',
        outline_bid: 'lesson-1',
      });
      expect(result.current.latestDraftMeta?.revision).toBe(9);
    });
  });

  it('does not clear current draft meta when a stale outline request fails', async () => {
    const consoleErrorSpy = jest
      .spyOn(console, 'error')
      .mockImplementation(() => undefined);
    const lessonOneDraftMeta = createDeferred<unknown>();
    mockGetShifuDraftMeta.mockImplementation(({ outline_bid }) => {
      if (outline_bid === 'lesson-1') {
        return lessonOneDraftMeta.promise;
      }
      return Promise.resolve({
        revision: 3,
        updated_at: '2026-06-30T06:37:42Z',
        updated_user: null,
      });
    });

    const { result } = renderHook(() => useShifu(), { wrapper });

    let lessonOnePromise: Promise<unknown> | null = null;
    await act(async () => {
      result.current.actions.setCurrentNode({
        bid: 'lesson-1',
        depth: 1,
      } as any);
      lessonOnePromise = result.current.actions.loadDraftMeta(
        'shifu-1',
        'lesson-1',
      );
    });

    await act(async () => {
      result.current.actions.setCurrentNode({
        bid: 'lesson-2',
        depth: 1,
      } as any);
      await result.current.actions.loadDraftMeta('shifu-1', 'lesson-2');
    });

    expect(result.current.latestDraftMeta?.revision).toBe(3);

    await act(async () => {
      lessonOneDraftMeta.reject(new Error('stale failure'));
      await lessonOnePromise;
    });

    expect(result.current.latestDraftMeta?.revision).toBe(3);
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      'Failed to load draft meta',
      expect.any(Error),
    );
    consoleErrorSpy.mockRestore();
  });
});

describe('useShifu outline-create analytics producers', () => {
  const creatorPaths = [
    'addRootOutline',
    'addSubOutline',
    'addSiblingOutline',
    'createChapter',
    'createOutline',
  ] as const;

  beforeEach(() => {
    jest.clearAllMocks();
    mockGetShifuDetail.mockResolvedValue({
      bid: 'course-1',
      name: 'Private course name',
      readonly: false,
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  const prepareCreatorPath = async (
    path: (typeof creatorPaths)[number],
    result: { current: ReturnType<typeof useShifu> },
    learningPermission?: LearningPermission,
  ) => {
    const settings = {
      name: 'Private outline name',
      ...(learningPermission && { learningPermission }),
      isHidden: false,
      systemPrompt: 'Private system prompt',
    } as const;

    if (path === 'addRootOutline') {
      return {
        parentBid: '',
        invoke: () => result.current.actions.addRootOutline(settings),
      };
    }

    if (path === 'createChapter') {
      const placeholder = {
        id: 'new_chapter',
        bid: 'new_chapter',
        parent_bid: '',
        name: 'Private outline name',
        position: '',
        depth: 0,
        children: [],
      };
      act(() => result.current.actions.setChapters([placeholder]));
      return {
        parentBid: '',
        invoke: () => result.current.actions.createChapter(placeholder),
      };
    }

    const lesson = {
      id: path === 'createOutline' ? 'new_lesson' : 'lesson-1',
      bid: path === 'createOutline' ? 'new_lesson' : 'lesson-1',
      parent_bid: 'chapter-1',
      name: 'Private outline name',
      position: '',
      depth: 1,
      children: [],
    };
    const parent = {
      id: 'chapter-1',
      bid: 'chapter-1',
      parent_bid: '',
      name: 'Private chapter name',
      position: '',
      depth: 0,
      children: [lesson],
    };
    act(() => result.current.actions.setChapters([parent]));

    if (path === 'addSubOutline') {
      return {
        parentBid: 'chapter-1',
        invoke: () => result.current.actions.addSubOutline(parent, settings),
      };
    }
    if (path === 'addSiblingOutline') {
      return {
        parentBid: 'chapter-1',
        invoke: () =>
          result.current.actions.addSiblingOutline(lesson, settings),
      };
    }
    return {
      parentBid: 'chapter-1',
      invoke: () => result.current.actions.createOutline(lesson),
    };
  };

  it.each(creatorPaths)(
    '%s emits only after success with the server-issued outline BID',
    async path => {
      const createdOutline = createDeferred<{
        bid: string;
        name: string;
        type: LearningPermission;
        is_hidden: boolean;
      }>();
      mockCreateOutline.mockReturnValue(createdOutline.promise);
      const { result } = renderHook(() => useShifu(), { wrapper });

      await act(async () => {
        await result.current.actions.loadShifu('course-1');
      });
      const { invoke, parentBid } = await prepareCreatorPath(path, result);

      let operation!: Promise<unknown>;
      act(() => {
        operation = invoke();
      });

      expect(mockCreateOutline).toHaveBeenCalledTimes(1);
      expect(mockCreateOutline.mock.calls[0][0]).not.toHaveProperty('type');
      expect(mockTrackEvent).not.toHaveBeenCalled();

      await act(async () => {
        createdOutline.resolve({
          bid: 'server-outline-1',
          name: 'Private outline name',
          type: 'normal',
          is_hidden: true,
        });
        await operation;
      });

      expect(result.current.cataData['server-outline-1']).toEqual(
        expect.objectContaining({ type: 'normal', is_hidden: true }),
      );
      const createdNode = result.current.chapters
        .flatMap(chapter => [chapter, ...(chapter.children || [])])
        .find(outline => outline.bid === 'server-outline-1');
      expect(createdNode).toEqual(
        expect.objectContaining({ type: 'normal', is_hidden: true }),
      );
      expect(mockTrackEvent).toHaveBeenCalledTimes(1);
      expect(mockTrackEvent).toHaveBeenCalledWith('creator_outline_create', {
        shifu_bid: 'course-1',
        outline_bid: 'server-outline-1',
        parent_bid: parentBid,
      });
      expect(mockTrackEvent.mock.calls[0][1]).not.toHaveProperty('name');
      expect(mockTrackEvent.mock.calls[0][1]).not.toHaveProperty('description');
      expect(mockTrackEvent.mock.calls[0][1]).not.toHaveProperty(
        'system_prompt',
      );
    },
  );

  it.each(creatorPaths)(
    '%s emits nothing when outline creation fails',
    async path => {
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => undefined);
      const createdOutline = createDeferred<{
        bid: string;
        name: string;
      }>();
      mockCreateOutline.mockReturnValue(createdOutline.promise);
      const { result } = renderHook(() => useShifu(), { wrapper });

      await act(async () => {
        await result.current.actions.loadShifu('course-1');
      });
      const { invoke } = await prepareCreatorPath(path, result);

      let operation!: Promise<unknown>;
      act(() => {
        operation = invoke();
      });
      const observedOperation = operation.catch(() => undefined);

      await act(async () => {
        createdOutline.reject(new Error('Private API error'));
        await observedOperation;
      });

      expect(mockCreateOutline).toHaveBeenCalledTimes(1);
      expect(mockTrackEvent).not.toHaveBeenCalled();
      expect(consoleErrorSpy).toHaveBeenCalled();
    },
  );
  it.each(
    (['addSubOutline', 'addSiblingOutline'] as const).flatMap(path =>
      (['guest', 'trial', 'normal'] as const).map(permission => ({
        path,
        permission,
      })),
    ),
  )(
    'preserves an explicit $permission selection in $path',
    async ({ path, permission }) => {
      mockCreateOutline.mockResolvedValue({
        bid: 'server-outline-1',
        name: 'Private outline name',
        type: permission,
        is_hidden: false,
      });
      const { result } = renderHook(() => useShifu(), { wrapper });
      await act(async () => {
        await result.current.actions.loadShifu('course-1');
      });
      const { invoke } = await prepareCreatorPath(path, result, permission);

      await act(async () => {
        await invoke();
      });

      expect(mockCreateOutline).toHaveBeenCalledWith(
        expect.objectContaining({ type: permission }),
      );
      expect(result.current.cataData['server-outline-1'].type).toBe(permission);
    },
  );

  it('keeps new chapter and lesson placeholders without an assigned permission', () => {
    const { result } = renderHook(() => useShifu(), { wrapper });
    act(() => result.current.actions.insertPlaceholderChapter());
    expect(result.current.chapters[0]).not.toHaveProperty('type');
    expect(result.current.cataData.new_chapter).not.toHaveProperty('type');

    const chapter = {
      id: 'chapter-1',
      bid: 'chapter-1',
      children: [],
      depth: 0,
    };
    act(() => result.current.actions.setChapters([chapter]));
    act(() => result.current.actions.insertPlaceholderLesson(chapter));
    expect(result.current.chapters[0].children?.[0]).not.toHaveProperty('type');
    expect(result.current.cataData.new_lesson).not.toHaveProperty('type');
  });
  it('lets the backend default a legacy sibling creation and uses its returned settings', async () => {
    mockCreateOutline.mockResolvedValue({
      bid: 'server-outline-1',
      name: 'Private outline name',
      type: 'trial',
      is_hidden: true,
    });
    const { result } = renderHook(() => useShifu(), { wrapper });
    await act(async () => {
      await result.current.actions.loadShifu('course-1');
    });
    const placeholder = {
      id: 'new_chapter',
      bid: 'new_chapter',
      name: 'Private outline name',
      parent_bid: 'chapter-1',
      children: [],
      depth: 1,
    };
    const chapter = {
      id: 'chapter-1',
      bid: 'chapter-1',
      children: [placeholder],
      depth: 0,
    };
    act(() => result.current.actions.setChapters([chapter]));
    await act(async () => {
      await result.current.actions.createSiblingUnit(placeholder);
    });

    expect(mockCreateOutline.mock.calls[0][0]).not.toHaveProperty('type');
    expect(result.current.chapters[0].children?.[0]).toEqual(
      expect.objectContaining({
        bid: 'server-outline-1',
        type: 'trial',
        is_hidden: true,
      }),
    );
    expect(result.current.cataData['server-outline-1']).toEqual(
      expect.objectContaining({ type: 'trial', is_hidden: true }),
    );
  });
});

describe('useShifu memory definition requests', () => {
  beforeEach(() => {
    localStorage.clear();
    mockGetProfileItemDefinitions.mockReset();
    mockGetProfileVariableUsage.mockReset();
  });

  it('omits the retired type filter while preserving scope, visibility and caching', async () => {
    mockGetProfileItemDefinitions.mockResolvedValue([
      {
        profile_id: 'system-1',
        profile_key: 'sys_user_nickname',
        profile_scope: 'system',
        profile_remark: 'Nickname',
        profile_type: 'text',
      },
      {
        profile_id: 'question-1',
        profile_key: 'What would you like to learn?',
        profile_scope: 'user',
        profile_type: 'text',
        is_hidden: false,
      },
      {
        profile_id: 'legacy-1',
        profile_key: 'legacy_key',
        profile_scope: 'user',
        profile_type: 'text',
        is_hidden: true,
      },
    ]);
    mockGetProfileVariableUsage.mockResolvedValue({
      used_keys: ['What would you like to learn?'],
      unused_keys: ['legacy_key'],
    });
    const { result } = renderHook(() => useShifu(), { wrapper });

    await act(async () => {
      await result.current.actions.refreshProfileDefinitions('course-memory');
    });

    expect(mockGetProfileItemDefinitions).toHaveBeenCalledWith({
      parent_id: 'course-memory',
    });
    expect(result.current.variables).toEqual([
      'What would you like to learn?',
      'legacy_key',
    ]);
    expect(result.current.systemVariables).toEqual([
      { name: 'sys_user_nickname', label: 'Nickname' },
    ]);
    expect(result.current.hiddenVariables).toEqual(['legacy_key']);
    expect(result.current.unusedVariables).toEqual(['legacy_key']);

    await act(async () => {
      await result.current.actions.refreshProfileDefinitions('course-memory');
    });

    expect(mockGetProfileItemDefinitions).toHaveBeenCalledTimes(1);
    expect(mockGetProfileVariableUsage).toHaveBeenCalledTimes(1);
  });
});
