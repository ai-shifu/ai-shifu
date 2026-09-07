import { useAskStateStore } from './useAskStateStore';

describe('Live follow-up history lesson scope', () => {
  beforeEach(() => useAskStateStore.getState().clearLessonScope());

  it('appends a committed turn to its active lesson', () => {
    const store = useAskStateStore.getState();
    store.ensureLessonScope('lesson-1');
    store.setAskList(
      'anchor-1',
      [{ type: 'ask', content: 'Question' }],
      'lesson-1',
    );

    expect(useAskStateStore.getState().askListByAnchorElementBid).toEqual({
      'anchor-1': [
        { type: 'ask', content: 'Question', shouldUseTypewriter: false },
      ],
    });
  });

  it('ignores a delayed commit after the lesson scope changes', () => {
    const store = useAskStateStore.getState();
    store.ensureLessonScope('lesson-1');
    store.ensureLessonScope('lesson-2');
    store.setAskList('anchor-2', [{ type: 'ask', content: 'New question' }]);
    const appendOldTurn = jest.fn(() => [
      { type: 'ask' as const, content: 'Old question' },
    ]);

    store.setAskList('anchor-1', appendOldTurn, 'lesson-1');

    expect(appendOldTurn).not.toHaveBeenCalled();
    expect(useAskStateStore.getState().askListByAnchorElementBid).toEqual({
      'anchor-2': [
        { type: 'ask', content: 'New question', shouldUseTypewriter: false },
      ],
    });
  });
});
