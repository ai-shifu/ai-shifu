import {
  initialProfileOnboardingConversationState,
  isProfileOnboardingTypewriterCandidate,
  profileOnboardingConversationReducer,
  resolveProfileOnboardingElement,
  resolveProfileRunState,
  resolveNextTurnIndex,
  isProfileSummaryPhase,
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

  it('accepts only the validated interaction even when another question is last', () => {
    const state = {
      ...initialProfileOnboardingConversationState,
      status: 'streaming' as const,
      items: [
        { ...interaction, interactionId: 'question-a' },
        {
          ...interaction,
          elementBid: 'question-2',
          interactionId: 'question-b',
        },
      ],
    };
    const accepted = profileOnboardingConversationReducer(state, {
      type: 'accept_submission',
      interactionId: 'question-a',
      userInput: 'First answer',
    });
    expect(accepted.items[0]).toMatchObject({
      finished: true,
      userInput: 'First answer',
    });
    expect(accepted.items[1]).toMatchObject({ finished: false });
    expect(accepted.items[1].userInput).toBeUndefined();
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

describe('native session turn state', () => {
  it('reads the authoritative native pending order and validated input result', () => {
    const event = {
      type: 'done',
      content: JSON.stringify({
        next_turn_index: 8,
        awaiting_input: true,
        input_accepted: false,
        pending_interaction_ids: ['first', 'second'],
      }),
    };
    expect(resolveNextTurnIndex(event)).toBe(8);
    expect(resolveProfileRunState(event)).toEqual({
      awaitingInput: true,
      inputAccepted: false,
      pendingInteractionIds: ['first', 'second'],
    });
    expect(
      isProfileSummaryPhase({ type: 'phase', content: { phase: 'summary' } }),
    ).toBe(true);
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
  it('retains a native question identity independently of its display element', () => {
    const element = resolveProfileOnboardingElement({
      type: 'interaction',
      generated_block_bid: 'display-question-1',
      interaction_id: 'native-question-1',
      content: '?[...Your answer]',
    });

    expect(element).toMatchObject({
      elementBid: 'display-question-1',
      interactionId: 'native-question-1',
      interaction: true,
    });
    expect(
      resolveProfileOnboardingElement({
        type: 'interaction',
        content: '?[...Legacy question]',
      }),
    ).not.toHaveProperty('interactionId');
  });

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
  it('keeps the same native pending question mounted when its turn slot changes', () => {
    const original = { ...interaction, interactionId: 'native-question' };
    const nextTurn = {
      ...original,
      elementBid: 'turn-2:interaction',
    };
    const items = upsertConversationItem([original], nextTurn);
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({
      interactionId: 'native-question',
      elementBid: interaction.elementBid,
      finished: false,
    });
  });

  it('replaces an uncommitted question token at its stable display element', () => {
    const firstQuestion = {
      ...interaction,
      interactionId: 'uncommitted-question',
    };
    const replacement = {
      ...interaction,
      interactionId: 'persisted-question',
    };

    const items = upsertConversationItem([firstQuestion], replacement);

    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({
      elementBid: interaction.elementBid,
      interactionId: 'persisted-question',
      interaction: true,
      finished: false,
    });
    expect(
      items.filter(item => item.interaction && !item.finished),
    ).toHaveLength(1);
  });

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

    const items = upsertConversationItem(
      [answeredInteraction, validationFeedback],
      interaction,
    );

    expect(items.map(item => item.elementBid)).toEqual([
      'question-1:feedback',
      'question-1',
    ]);
    expect(items[1].userInput).toBeUndefined();
  });
});
