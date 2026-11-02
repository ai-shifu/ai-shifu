import { act, renderHook, waitFor } from '@testing-library/react';
import { useLessonResetStatus } from './use-lesson-reset-status';
import { getLessonResetStatus } from '@/api/lesson';

const mockEnv = { courseId: 'course' };
const mockSystem = { previewMode: false };
let mockToken = 'authenticated-token';
const mockUser: {
  userInfo: { user_id: string } | null;
  isInitialized: boolean;
  getToken: () => string;
} = {
  userInfo: { user_id: 'learner' },
  isInitialized: true,
  getToken: () => mockToken,
};
const mockCourse = { resettingLessonId: '' };
jest.mock('@/api/lesson', () => ({ getLessonResetStatus: jest.fn() }));
jest.mock('@/store/env-store', () => ({
  useEnvStore: (selector: (state: typeof mockEnv) => unknown) =>
    selector(mockEnv),
}));
jest.mock('@/store/use-system-store', () => ({
  useSystemStore: (selector: (state: typeof mockSystem) => unknown) =>
    selector(mockSystem),
}));
jest.mock('@/store/use-user-store', () => ({
  useUserStore: (selector: (state: typeof mockUser) => unknown) =>
    selector(mockUser),
}));
jest.mock('@/store/use-course-store', () => ({
  useCourseStore: (selector: (state: typeof mockCourse) => unknown) =>
    selector(mockCourse),
}));

beforeEach(() => {
  jest.clearAllMocks();
  mockUser.isInitialized = true;
  mockUser.userInfo = { user_id: 'learner' };
  mockToken = 'authenticated-token';
  mockCourse.resettingLessonId = '';
  (getLessonResetStatus as jest.Mock)
    .mockReset()
    .mockResolvedValue({ can_reset: true });
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
  mockUser.userInfo = { user_id: 'other' };
  rerender({ lesson: 'new' });
  await waitFor(() => expect(result.current.phase).toBe('ready'));
  await act(async () => resolve({ can_reset: false }));
  expect(result.current.phase).toBe('ready');
});

it('enables a first-visit guest with a valid token but no loaded profile', async () => {
  mockUser.userInfo = null;
  mockToken = 'guest-token';
  const { result } = renderHook(() => useLessonResetStatus('lesson', true));
  await waitFor(() => expect(result.current.phase).toBe('ready'));
  expect(getLessonResetStatus).toHaveBeenCalledTimes(1);
});

it('does not query when guest initialization failed to obtain an identity', () => {
  mockUser.userInfo = null;
  mockToken = '';
  const { result } = renderHook(() => useLessonResetStatus('lesson', true));
  expect(result.current.phase).toBe('idle');
  expect(getLessonResetStatus).not.toHaveBeenCalled();
});

it('refreshes after a reset completes and surfaces the server rejection', async () => {
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
});

it('marks the lesson exhausted when the reset itself answers 4021', async () => {
  const { result } = renderHook(() => useLessonResetStatus('lesson', true));
  await waitFor(() => expect(result.current.phase).toBe('ready'));
  act(() => result.current.setFailure({ code: 4021 }));
  expect(result.current.phase).toBe('exhausted');
  act(() => result.current.setFailure({ code: 500 }));
  expect(result.current.phase).toBe('exhausted');
});

it('falls back to ready when availability cannot be read', async () => {
  (getLessonResetStatus as jest.Mock).mockRejectedValue(new Error('offline'));
  const { result } = renderHook(() => useLessonResetStatus('lesson', true));
  await waitFor(() => expect(result.current.phase).toBe('ready'));
});
