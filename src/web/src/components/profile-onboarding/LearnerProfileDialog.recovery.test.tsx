import React from 'react';
import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import type { ComponentProps } from 'react';
import {
  completeGuidedProfileOnboarding,
  createProfileOnboardingSession,
  getLearnerProfile,
  getProfileOnboarding,
  runProfileOnboardingSession,
  updateLearnerProfile,
} from '@/api/learner-profile';
import type ContentBlock from '@/components/chat/ContentBlock';
import LearnerProfileDialog from './LearnerProfileDialog';
import { useLearnerProfileDialogController } from './use-learner-profile-dialog-controller';

jest.mock('@/api/learner-profile', () => ({
  completeGuidedProfileOnboarding: jest.fn(),
  createProfileOnboardingSession: jest.fn(),
  getLearnerProfile: jest.fn(),
  getProfileOnboarding: jest.fn(),
  isProfileOnboardingStatus: (value: unknown) => Boolean(value),
  optimizeLearnerProfile: jest.fn(),
  runProfileOnboardingSession: jest.fn(),
  submitProfileOnboardingAssistantAnswers: jest.fn(),
  updateLearnerProfile: jest.fn(),
}));

jest.mock('@/components/chat/ContentBlock', () => ({
  __esModule: true,
  default: ({
    item,
    blockBid,
    onSend,
  }: ComponentProps<typeof ContentBlock>) => (
    <button
      type='button'
      disabled={item.readonly}
      onClick={() =>
        onSend(
          {
            variableName: 'goal',
            inputText: item.user_input ? 'Edited answer' : 'Original answer',
          },
          blockBid,
        )
      }
    >
      {item.content}
    </button>
  ),
}));

jest.mock('markdown-flow-ui/scroll', () => ({
  ScrollToBottomControl: () => null,
}));

jest.mock('remark-flow', () =>
  jest.requireActual('remark-flow/dist/variable-name'),
);
jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { resolvedLanguage: 'en-US', language: 'en-US' },
  }),
}));

const mockTrackEvent = jest.fn();
jest.mock('@/hooks/use-tracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));
jest.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: jest.fn() }),
}));

const savedProfile = {
  learner_profile: 'Saved account profile',
  learner_profile_updated_at: '2026-11-07T03:00:00Z',
  has_learner_profile: true,
  nickname: 'Saved nickname',
  max_length: 1000,
  nickname_max_length: 64,
};
const expiredSessionId = '0123456789abcdef0123456789abcdef';
const freshSessionId = 'fedcba9876543210fedcba9876543210';
const dialogProps = {
  open: true,
  exitPolicy: 'blocking' as const,
  draftStorageScope: 'recovery-user',
  onClose: jest.fn(),
};

beforeEach(() => {
  jest.clearAllMocks();
  jest.mocked(getLearnerProfile).mockResolvedValue(savedProfile);
  jest.mocked(getProfileOnboarding).mockResolvedValue({
    ...savedProfile,
    enabled: true,
    guided_available: true,
    should_show: false,
    presentation: 'hidden',
    handled: true,
  });
});

it('reviews and explicitly saves a fresh result after an expired edit restarts collection', async () => {
  jest
    .mocked(createProfileOnboardingSession)
    .mockResolvedValueOnce({
      session_id: expiredSessionId,
      turn_index: 0,
      done: false,
      expires_in: 1800,
    })
    .mockResolvedValueOnce({
      session_id: freshSessionId,
      turn_index: 0,
      done: false,
      expires_in: 1800,
    });
  jest
    .mocked(completeGuidedProfileOnboarding)
    .mockResolvedValue({ ...savedProfile, learner_profile: 'Fresh draft' });
  jest.mocked(runProfileOnboardingSession).mockImplementation(request => {
    const expired = request.sessionId === expiredSessionId;
    queueMicrotask(() => {
      if (request.rewind) {
        request.onMessage({
          type: 'error',
          content: 'transient_markdownflow_session_not_found',
        });
      } else if (!request.userInput) {
        request.onMessage({
          type: 'interaction',
          generated_block_bid: 'goal',
          interaction_id: 'goal',
          content: expired ? 'Expired question' : 'Fresh question',
        });
        request.onMessage({
          type: 'done',
          is_terminal: true,
          content: {
            done: false,
            next_turn_index: 1,
            pending_interaction_ids: ['goal'],
          },
        });
      } else {
        request.onMessage({
          type: 'done',
          is_terminal: true,
          content: {
            done: true,
            input_accepted: true,
            next_turn_index: 2,
            pending_interaction_ids: [],
            rewindable_interaction_ids: ['goal'],
            profile_draft: expired ? 'Expired draft' : 'Fresh draft',
            ...(expired ? { nickname: 'Expired nickname' } : {}),
          },
        });
      }
    });
    return { close: jest.fn() };
  });

  render(<LearnerProfileDialog {...dialogProps} />);
  await screen.findByDisplayValue(savedProfile.learner_profile);
  fireEvent.click(
    screen.getByTestId('learner-profile-interactive-collection-mobile'),
  );
  fireEvent.click(
    await screen.findByRole('button', { name: 'Expired question' }),
  );
  await screen.findByRole('button', {
    name: 'module.profileOnboarding.guided.reviewCollection',
  });
  fireEvent.click(screen.getByRole('button', { name: 'Expired question' }));
  const confirmation = await screen.findByRole('dialog', {
    name: 'module.chat.regenerateConfirmTitle',
  });
  fireEvent.click(
    within(confirmation).getByRole('button', { name: 'common.core.ok' }),
  );
  fireEvent.click(
    await screen.findByRole('button', {
      name: 'module.profileOnboarding.guided.retry',
    }),
  );
  const freshQuestion = await screen.findByRole('button', {
    name: 'Fresh question',
  });
  expect(
    screen.queryByRole('button', {
      name: 'module.profileOnboarding.guided.reviewCollection',
    }),
  ).not.toBeInTheDocument();
  expect(jest.mocked(getLearnerProfile)).toHaveBeenCalledTimes(1);
  expect(completeGuidedProfileOnboarding).not.toHaveBeenCalled();
  expect(updateLearnerProfile).not.toHaveBeenCalled();

  fireEvent.click(freshQuestion);
  fireEvent.click(
    await screen.findByRole('button', {
      name: 'module.profileOnboarding.guided.reviewCollection',
    }),
  );
  expect(await screen.findByDisplayValue('Fresh draft')).toBeInTheDocument();
  expect(
    screen.getByLabelText('module.profileOnboarding.dialog.nicknameLabel'),
  ).toHaveValue(savedProfile.nickname);
  fireEvent.click(
    screen.getByRole('button', { name: 'module.profileOnboarding.complete' }),
  );
  await waitFor(() =>
    expect(completeGuidedProfileOnboarding).toHaveBeenCalledWith({
      learner_profile: 'Fresh draft',
      trigger_source: 'settings',
      session_id: freshSessionId,
    }),
  );
  expect(dialogProps.onClose).toHaveBeenCalledWith('saved');
});

it('accepts one result per session and ignores results from the replaced session', async () => {
  const { result } = renderHook(() =>
    useLearnerProfileDialogController(dialogProps),
  );
  await waitFor(() => expect(result.current.derived.loaded).toBe(true));
  act(result.current.requestCollection);
  act(() => {
    result.current.conversationProps.onSessionStarted?.(expiredSessionId);
    result.current.conversationProps.onDraftReady(
      'Expired draft',
      expiredSessionId,
      'Expired nickname',
    );
  });
  act(() =>
    result.current.conversationProps.onDraftReady(
      'Duplicate draft',
      expiredSessionId,
    ),
  );
  expect(result.current.state.collectionResult?.draft).toBe('Expired draft');

  act(() =>
    result.current.conversationProps.onSessionStarted?.(freshSessionId),
  );
  expect(result.current.state.collectionResult).toBeNull();
  expect(result.current.state.form.profile).toBe(savedProfile.learner_profile);
  expect(result.current.state.form.nickname).toBe(savedProfile.nickname);
  expect(result.current.state.form.savedProfile).toBe(
    savedProfile.learner_profile,
  );
  act(() =>
    result.current.conversationProps.onDraftReady(
      'Late expired draft',
      expiredSessionId,
    ),
  );
  expect(result.current.state.collectionResult).toBeNull();
  act(() =>
    result.current.conversationProps.onDraftReady(
      'Fresh draft',
      freshSessionId,
    ),
  );
  expect(result.current.state.collectionResult?.draft).toBe('Fresh draft');
  act(() =>
    result.current.conversationProps.onDraftReady(
      'Duplicate fresh draft',
      freshSessionId,
    ),
  );
  expect(result.current.state.collectionResult?.draft).toBe('Fresh draft');
});
