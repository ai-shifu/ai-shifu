import { act, renderHook } from '@testing-library/react';
import { uploadLearnerImage } from '@/api/learning';
import { useLearnerImages } from './use-learner-images';
import { toast } from './use-toast';

const mockTrack = jest.fn();
jest.mock('@/api/learning', () => ({ uploadLearnerImage: jest.fn() }));
jest.mock('./use-tracking', () => ({
  useTracking: () => ({ trackEvent: mockTrack }),
}));
jest.mock('./use-toast', () => ({ toast: jest.fn() }));
jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const upload = jest.mocked(uploadLearnerImage);
const file = () =>
  new File(['image'], 'private-homework.png', { type: 'image/png' });

beforeEach(() => {
  jest.clearAllMocks();
  upload.mockResolvedValue('/api/storage/courses/learner-images/image.png');
  mockTrack.mockResolvedValue(undefined);
});

it('tracks one attempt and success per accepted upload, without content or rerender duplicates', async () => {
  const { result, rerender } = renderHook(() =>
    useLearnerImages('lesson', 'answer'),
  );
  expect(mockTrack).not.toHaveBeenCalled();
  await act(() => result.current.addFiles([file()]));
  rerender();
  expect(result.current.images).toHaveLength(1);
  expect(mockTrack.mock.calls).toEqual([
    ['learner_image_upload_started', { surface: 'answer' }],
    [
      'learner_image_upload_finished',
      { surface: 'answer', outcome: 'success' },
    ],
  ]);
  expect(JSON.stringify(mockTrack.mock.calls)).not.toMatch(
    /private|homework|image.png|filename|url|error/i,
  );
});

it('retains earlier attachments on failure and reports exactly one failed result', async () => {
  const { result } = renderHook(() => useLearnerImages('lesson', 'follow_up'));
  await act(() => result.current.addFiles([file()]));
  upload.mockRejectedValueOnce(new Error('private raw error'));
  await act(() => result.current.addFiles([file()]));
  expect(result.current.images).toHaveLength(1);
  expect(mockTrack.mock.calls.at(-1)).toEqual([
    'learner_image_upload_finished',
    { surface: 'follow_up', outcome: 'failed' },
  ]);
  expect(result.current.uploading).toBe(false);
  expect(toast).toHaveBeenCalled();
});

it('excludes previews from analytics while preserving uploads', async () => {
  const { result } = renderHook(() =>
    useLearnerImages('preview', 'answer', true),
  );
  await act(() => result.current.addFiles([file()]));
  expect(result.current.images).toHaveLength(1);
  expect(mockTrack).not.toHaveBeenCalled();
});

it('fails open when tracking throws or rejects', async () => {
  mockTrack
    .mockImplementationOnce(() => {
      throw new Error('tracker');
    })
    .mockRejectedValueOnce(new Error('offline'));
  const { result } = renderHook(() => useLearnerImages('lesson', 'answer'));
  await act(() => result.current.addFiles([file()]));
  expect(result.current.images).toHaveLength(1);
  expect(upload).toHaveBeenCalledTimes(1);
});

it('refuses unsupported, empty, oversized and excessive selections before tracking or uploading', async () => {
  const { result } = renderHook(() => useLearnerImages('lesson', 'answer'));
  const oversized = file();
  Object.defineProperty(oversized, 'size', { value: 5 * 1024 * 1024 + 1 });
  for (const files of [
    [new File(['svg'], 'private.svg', { type: 'image/svg+xml' })],
    [new File([], 'empty.png', { type: 'image/png' })],
    [oversized],
    Array.from({ length: 5 }, file),
  ])
    await act(() => result.current.addFiles(files));
  expect(upload).not.toHaveBeenCalled();
  expect(mockTrack).not.toHaveBeenCalled();
});

it('ignores duplicate in-flight actions and never leaks an old upload into another lesson', async () => {
  let resolveUpload!: (url: string) => void;
  upload.mockImplementationOnce(
    () =>
      new Promise(resolve => {
        resolveUpload = resolve;
      }),
  );
  const { result, rerender } = renderHook(
    ({ scope }) => useLearnerImages(scope, 'answer'),
    { initialProps: { scope: 'first' } },
  );
  let pending!: Promise<void>;
  act(() => {
    pending = result.current.addFiles([file()]);
  });
  await act(() => result.current.addFiles([file()]));
  expect(upload).toHaveBeenCalledTimes(1);
  rerender({ scope: 'second' });
  await act(async () => {
    resolveUpload('private-old-image');
    await pending;
  });
  expect(result.current.images).toEqual([]);
  expect(result.current.uploading).toBe(false);
  expect(mockTrack).toHaveBeenCalledTimes(2);
});
