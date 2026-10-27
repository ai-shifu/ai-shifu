import { startPreviewRewindTracking } from './previewRewindTracking';

const context = {
  preview: true,
  anchor: 'question-id',
  answering: true,
  shifuBid: 'course-id',
  outlineBid: 'lesson-id',
  learningMode: 'read',
};

it('emits only the allowed identifiers and enums, with one terminal result', () => {
  const trackEvent = jest.fn();
  const finish = startPreviewRewindTracking({ ...context, trackEvent });
  expect(trackEvent.mock.calls).toEqual([
    [
      'teacher_preview_rewind_start',
      {
        shifu_bid: 'course-id',
        outline_bid: 'lesson-id',
        operation: 'answer_edit',
        learning_mode: 'read',
      },
    ],
  ]);
  finish?.('success');
  finish?.('failed');
  finish?.('cancelled');
  expect(trackEvent.mock.calls).toHaveLength(2);
  expect(trackEvent.mock.calls[1]).toEqual([
    'teacher_preview_rewind_result',
    {
      shifu_bid: 'course-id',
      outline_bid: 'lesson-id',
      operation: 'answer_edit',
      learning_mode: 'read',
      result: 'success',
    },
  ]);
  expect(JSON.stringify(trackEvent.mock.calls)).not.toContain('question-id');
});

it.each([{ preview: false }, { anchor: undefined }])(
  'excludes ordinary and published runs %j',
  change => {
    const trackEvent = jest.fn();
    expect(
      startPreviewRewindTracking({ ...context, ...change, trackEvent }),
    ).toBeUndefined();
    expect(trackEvent).not.toHaveBeenCalled();
  },
);

it.each(['success', 'failed', 'cancelled'] as const)(
  'reports regeneration in listen mode: %s',
  result => {
    const trackEvent = jest.fn();
    startPreviewRewindTracking({
      ...context,
      answering: false,
      learningMode: 'listen',
      trackEvent,
    })?.(result);
    expect(trackEvent).toHaveBeenLastCalledWith(
      'teacher_preview_rewind_result',
      {
        shifu_bid: 'course-id',
        outline_bid: 'lesson-id',
        operation: 'regenerate',
        learning_mode: 'listen',
        result,
      },
    );
  },
);

it.each(['sync', 'async'])(
  'does not propagate %s tracking failure',
  async kind => {
    const trackEvent = jest.fn(() => {
      if (kind === 'sync') throw new Error('Tracking failed');
      return Promise.reject(new Error('Tracking failed'));
    });
    const finish = startPreviewRewindTracking({ ...context, trackEvent });
    expect(() => finish?.('success')).not.toThrow();
    await Promise.resolve();
    expect(trackEvent).toHaveBeenCalledTimes(2);
  },
);
