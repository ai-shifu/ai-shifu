import {
  initialProfileOnboardingConversationState,
  profileOnboardingConversationReducer,
  type ProfileOnboardingConversationItem,
} from './profileOnboardingConversationModel';

const interaction: ProfileOnboardingConversationItem = {
  content: '?[%{{goal}}...Goal?]',
  elementBid: 'question-1',
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
