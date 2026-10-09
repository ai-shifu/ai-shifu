import request from '@/lib/request';
import { useSystemStore } from '@/store/useSystemStore';
import { resetChapter } from './lesson';

jest.mock('@/lib/request', () => ({
  __esModule: true,
  default: { delete: jest.fn() },
}));
jest.mock('@/store/useSystemStore', () => ({
  useSystemStore: { getState: jest.fn() },
}));
jest.mock('@/store/envStore', () => ({
  useEnvStore: { getState: jest.fn(() => ({ courseId: 'course' })) },
}));

describe('lesson restart scope', () => {
  it.each([true, false])(
    'sends explicit preview scope %s',
    async previewMode => {
      (useSystemStore.getState as jest.Mock).mockReturnValue({ previewMode });
      await resetChapter({ lessonId: 'lesson' });
      expect(request.delete).toHaveBeenLastCalledWith(
        `/api/learn/shifu/course/records/lesson?preview_mode=${previewMode}`,
      );
    },
  );
});
