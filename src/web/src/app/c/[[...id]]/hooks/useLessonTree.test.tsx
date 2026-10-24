import { act, renderHook } from '@testing-library/react';
import { getLessonTree } from '@/api/lesson';
import { useLessonTree } from './useLessonTree';

jest.mock('@/api/lesson', () => ({ getLessonTree: jest.fn() }));
jest.mock('@/api/studyV2', () => ({
  LEARNING_PERMISSION: {
    NORMAL: 'normal',
    TRIAL: 'trial',
    GUEST: 'guest',
  },
}));
jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: jest.fn() }),
}));
jest.mock('@/store/envStore', () => ({
  useEnvStore: { getState: () => ({ courseId: 'guide-course' }) },
}));
jest.mock('@/store/useSystemStore', () => ({
  useSystemStore: (selector: (state: { previewMode: boolean }) => unknown) =>
    selector({ previewMode: false }),
}));
jest.mock('@/store', () => ({
  useUserStore: (selector: (state: { isLoggedIn: boolean }) => unknown) =>
    selector({ isLoggedIn: true }),
}));
jest.mock('@/store/useCourseStore', () => ({
  useCourseStore: (selector: (state: { openPayModal: jest.Mock }) => unknown) =>
    selector({ openPayModal: jest.fn() }),
}));

const mockGetLessonTree = getLessonTree as jest.Mock;

describe('useLessonTree authored language metadata', () => {
  beforeEach(() => {
    jest.clearAllMocks();
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
