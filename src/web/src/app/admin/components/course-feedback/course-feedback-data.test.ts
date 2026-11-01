import { ErrorWithCode } from '@/lib/request';
import { resolveRequestErrorState } from './course-feedback-data';

jest.mock('@/store', () => ({
  __esModule: true,
  useEnvStore: jest.fn(),
}));

describe('course feedback data helpers', () => {
  test('resolveRequestErrorState keeps codes and falls back for unknown errors', () => {
    expect(
      resolveRequestErrorState(new ErrorWithCode('denied', 403), 'fallback'),
    ).toEqual({ message: 'denied', code: 403 });
    expect(resolveRequestErrorState(new Error('boom'), 'fallback')).toEqual({
      message: 'boom',
    });
    expect(resolveRequestErrorState('oops', 'fallback')).toEqual({
      message: 'fallback',
    });
  });
});
