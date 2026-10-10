import { act, renderHook, waitFor } from '@testing-library/react';
import { useLessonResetStatus } from './useLessonResetStatus';
import { getLessonResetStatus } from '@/api/lesson';

const mockEnv = { courseId: 'course' };
const mockSystem = { previewMode: false };
const mockUser = { userInfo: { user_id: 'learner' }, isInitialized: true };
const mockCourse = { resettingLessonId: '' };
jest.mock('@/api/lesson', () => ({ getLessonResetStatus: jest.fn() }));
jest.mock('@/store/envStore', () => ({
  useEnvStore: (selector: any) => selector(mockEnv),
}));
jest.mock('@/store/useSystemStore', () => ({
  useSystemStore: (selector: any) => selector(mockSystem),
}));
jest.mock('@/store/useUserStore', () => ({
  useUserStore: (selector: any) => selector(mockUser),
}));
jest.mock('@/store/useCourseStore', () => ({
  useCourseStore: (selector: any) => selector(mockCourse),
}));

beforeEach(() => {
  jest.clearAllMocks();
  mockUser.isInitialized = true;
  mockUser.userInfo.user_id = 'learner';
  mockCourse.resettingLessonId = '';
  (getLessonResetStatus as jest.Mock).mockResolvedValue({ can_reset: true });
});

it('waits for learner initialization and only queries an active reset surface', async () => {
  mockUser.isInitialized = false;
  const { result, rerender } = renderHook(
    ({ active }) => useLessonResetStatus('lesson', active),
    { initialProps: { active: false } },
  );
  expect(getLessonResetStatus).not.toHaveBeenCalled();
  rerender({ active: true });
  expect(result.current.phase).toBe('idle');
  expect(getLessonResetStatus).not.toHaveBeenCalled();
  mockUser.isInitialized = true;
  rerender({ active: true });
  await waitFor(() => expect(result.current.phase).toBe('ready'));
});

it('ignores a stale availability response after changing learner or lesson', async () => {
  let resolve!: (value: { can_reset: boolean }) => void;
  (getLessonResetStatus as jest.Mock).mockReturnValueOnce(
    new Promise(done => {
      resolve = done;
    }),
  );
  const { result, rerender } = renderHook(
    ({ lesson }) => useLessonResetStatus(lesson, true),
    { initialProps: { lesson: 'old' } },
  );
  mockUser.userInfo.user_id = 'other';
  rerender({ lesson: 'new' });
  await waitFor(() => expect(result.current.phase).toBe('ready'));
  await act(async () => resolve({ can_reset: false }));
  expect(result.current.phase).toBe('ready');
});

it('refreshes after reset completes and surfaces the terminal server rejection', async () => {
  const { result, rerender } = renderHook(() =>
    useLessonResetStatus('lesson', true),
  );
  await waitFor(() => expect(result.current.phase).toBe('ready'));
  mockCourse.resettingLessonId = 'lesson';
  rerender();
  (getLessonResetStatus as jest.Mock).mockResolvedValue({ can_reset: false });
  mockCourse.resettingLessonId = '';
  rerender();
  await waitFor(() => expect(result.current.phase).toBe('exhausted'));
  act(() => result.current.setFailure({ code: 4022 }));
  expect(result.current.phase).toBe('unavailable');
});

it('makes a failed availability read unavailable, without enabling reset', async () => {
  (getLessonResetStatus as jest.Mock).mockRejectedValue(new Error('offline'));
  const { result } = renderHook(() => useLessonResetStatus('lesson', true));
  await waitFor(() => expect(result.current.phase).toBe('unavailable'));
});
