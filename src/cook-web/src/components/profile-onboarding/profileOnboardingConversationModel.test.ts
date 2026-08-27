import {
  initialProfileOnboardingConversationState,
  isProfileOnboardingTypewriterCandidate,
  profileOnboardingConversationReducer,
  resolveProfileOnboardingElement,
  syncProfileOnboardingTypewriterCache,
  type ProfileOnboardingConversationItem,
  upsertConversationItem,
} from './profileOnboardingConversationModel';

const interaction: ProfileOnboardingConversationItem = {
  content: '?[%{{goal}}...Goal?]',
  elementBid: 'question-1',
  elementType: 'interaction',
  interaction: true,
  finished: false,
};

describe('profileOnboardingConversationReducer', () => {
  it('models creation, streaming, input, and completion explicitly', () => {
    const streaming = profileOnboardingConversationReducer(
      initialProfileOnboardingConversationState,
      { type: 'start_run' },
    );
    expect(streaming.status).toBe('streaming');

    const withQuestion = profileOnboardingConversationReducer(streaming, {
      type: 'receive_item',
      item: interaction,
    });
    expect(withQuestion.runHasContent).toBe(true);

    const awaitingInput = profileOnboardingConversationReducer(withQuestion, {
      type: 'await_input',
    });
    expect(awaitingInput.status).toBe('awaiting_input');

    const answered = profileOnboardingConversationReducer(awaitingInput, {
      type: 'accept_submission',
      userInput: 'Learn AI',
    });
    expect(answered.items[0]).toMatchObject({
      finished: true,
      userInput: 'Learn AI',
    });

    const nextRun = profileOnboardingConversationReducer(answered, {
      type: 'start_run',
    });
    expect(
      profileOnboardingConversationReducer(nextRun, { type: 'complete' })
        .status,
    ).toBe('completed');
  });

  it('classifies retryable and fatal failures', () => {
    const retryable = profileOnboardingConversationReducer(
      initialProfileOnboardingConversationState,
      { type: 'fail', retryable: true },
    );
    expect(retryable.status).toBe('retryable_error');

    const fatal = profileOnboardingConversationReducer(
      initialProfileOnboardingConversationState,
      { type: 'fail', retryable: false },
    );
    expect(fatal.status).toBe('fatal_error');
  });

  it('ignores terminal and interaction events that arrive in invalid states', () => {
    const streaming = profileOnboardingConversationReducer(
      initialProfileOnboardingConversationState,
      { type: 'start_run' },
    );
    const completed = profileOnboardingConversationReducer(streaming, {
      type: 'complete',
    });

    expect(
      profileOnboardingConversationReducer(completed, {
        type: 'receive_item',
        item: interaction,
      }),
    ).toBe(completed);
    expect(
      profileOnboardingConversationReducer(completed, {
        type: 'fail',
        retryable: true,
      }),
    ).toBe(completed);
    expect(
      profileOnboardingConversationReducer(
        initialProfileOnboardingConversationState,
        { type: 'accept_submission', userInput: 'late' },
      ),
    ).toBe(initialProfileOnboardingConversationState);
  });
});

describe('syncProfileOnboardingTypewriterCache', () => {
  it('keeps suppressed text finished when its content changes on restore', () => {
    const textItem: ProfileOnboardingConversationItem = {
      content: 'Longer guidance',
      elementBid: 'text-1',
      elementType: 'text',
      interaction: false,
      finished: true,
    };

    expect(
      syncProfileOnboardingTypewriterCache(
        [textItem],
        {
          'text-1': {
            content: 'Guidance',
            isFinished: true,
            isSuppressed: true,
          },
        },
        false,
      )['text-1'],
    ).toMatchObject({ isFinished: true, isSuppressed: true });
  });
});

describe('resolveProfileOnboardingElement', () => {
  it('preserves HTML element types from legacy content events', () => {
    const element = resolveProfileOnboardingElement({
      type: 'content',
      element_type: 'html',
      generated_block_bid: 'html-1',
      content: '<div>Visual card</div>',
    });

    expect(element).toMatchObject({
      content: '<div>Visual card</div>',
      elementBid: 'html-1',
      elementType: 'html',
      interaction: false,
    });
    expect(element && isProfileOnboardingTypewriterCandidate(element)).toBe(
      false,
    );
  });
});

describe('upsertConversationItem', () => {
  it('moves a rejected interaction behind its new validation feedback', () => {
    const answeredInteraction = {
      ...interaction,
      finished: true,
      userInput: 'invalid answer',
    };
    const validationFeedback: ProfileOnboardingConversationItem = {
      content: 'Please choose one of the available options.',
      elementBid: 'question-1:feedback',
      elementType: 'text',
      interaction: false,
      finished: true,
    };

    expect(
      upsertConversationItem(
        [answeredInteraction, validationFeedback],
        interaction,
      ).map(item => item.elementBid),
    ).toEqual(['question-1:feedback', 'question-1']);
  });
});
