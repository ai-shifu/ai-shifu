import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { deserialize, serialize } from 'node:v8';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/Dialog';
import ProfileOnboardingConversation, {
  type ProfileOnboardingRunSession,
} from './ProfileOnboardingConversation';

const mockToast = jest.fn();
jest.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('@/api/learning', () => ({
  LESSON_FEEDBACK_INTERACTION_MARKER: 'sys_lesson_feedback_score',
  SYS_INTERACTION_TYPE: {
    NEXT_CHAPTER: '_sys_next_chapter',
    PAY: '_sys_pay',
    LOGIN: '_sys_login',
  },
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { resolvedLanguage: 'en-US' },
  }),
}));

jest.mock('markdown-flow-ui/scroll', () => ({
  ScrollToBottomControl: () => null,
}));

jest.mock('remark-flow', () =>
  jest.requireActual('remark-flow/dist/variable-name'),
);

const originalStructuredClone = globalThis.structuredClone;
const profileTitle = 'Personalization';

beforeAll(() => {
  globalThis.structuredClone ??= value => deserialize(serialize(value));
});

afterAll(() => {
  globalThis.structuredClone = originalStructuredClone;
});

beforeEach(() => {
  mockToast.mockReset();
});

it('prefills an editable answer and confirms regeneration with the real MarkdownFlow input', async () => {
  const user = userEvent.setup();
  const onRewindAccepted = jest.fn();
  const runSession = jest.fn<
    ReturnType<ProfileOnboardingRunSession>,
    Parameters<ProfileOnboardingRunSession>
  >(({ expectedTurnIndex, onMessage, rewind }) => {
    queueMicrotask(() => {
      const initial = expectedTurnIndex === 0;
      const interactionId = initial ? 'goal' : rewind ? 'replacement' : 'pace';
      const prompt = initial
        ? 'Describe your goal'
        : rewind
          ? 'Describe your revised plan'
          : 'Describe your pace';

      if (rewind) {
        onMessage({
          type: 'rewind',
          content: { interaction_id: 'goal' },
        });
      }
      onMessage({
        type: 'interaction',
        generated_block_bid: `display-${interactionId}`,
        interaction_id: interactionId,
        content: `?[{{${interactionId}}}...${prompt}]`,
      });
      onMessage({
        type: 'done',
        is_terminal: true,
        content: {
          done: false,
          next_turn_index: expectedTurnIndex + 1,
          pending_interaction_ids: [interactionId],
          rewindable_interaction_ids: initial ? [] : ['goal'],
          input_accepted: !initial,
        },
      });
    });
    return { close: jest.fn() };
  });

  render(
    <Dialog open>
      <DialogContent aria-describedby={undefined}>
        <DialogTitle>{profileTitle}</DialogTitle>
        <ProfileOnboardingConversation
          createSession={async () => ({ session_id: 'rewind-profile' })}
          runSession={runSession}
          onRewindAccepted={onRewindAccepted}
          onDraftReady={jest.fn()}
          onError={jest.fn()}
        />
      </DialogContent>
    </Dialog>,
  );

  const goal = await screen.findByPlaceholderText('Describe your goal');
  await user.type(goal, 'Read faster{Enter}');
  await screen.findByPlaceholderText('Describe your pace');
  expect(goal).toHaveValue('Read faster');
  expect(goal).toBeEnabled();

  await user.clear(goal);
  await user.type(goal, 'Write clearly{Enter}');
  const dialog = () =>
    screen.getByRole('dialog', { name: 'module.chat.regenerateConfirmTitle' });
  await user.click(
    within(dialog()).getByRole('button', { name: 'common.core.cancel' }),
  );
  expect(runSession).toHaveBeenCalledTimes(2);

  await user.type(goal, '{Enter}');
  await user.click(
    within(dialog()).getByRole('button', { name: 'common.core.ok' }),
  );
  await screen.findByPlaceholderText('Describe your revised plan');
  expect(runSession).toHaveBeenLastCalledWith(
    expect.objectContaining({
      expectedTurnIndex: 2,
      expectedInteractionId: 'goal',
      userInput: { goal: ['Write clearly'] },
      rewind: true,
    }),
  );
  expect(
    screen.queryByPlaceholderText('Describe your pace'),
  ).not.toBeInTheDocument();
  await waitFor(() => expect(onRewindAccepted).toHaveBeenCalledTimes(1));
});

it.each([false, true])(
  'notifies and starts fresh after an invalid edit even when toast throws=%s',
  async toastThrows => {
    const user = userEvent.setup();
    if (toastThrows) {
      mockToast.mockImplementation(() => {
        throw new Error('Notification unavailable');
      });
    }
    const createSession = jest
      .fn()
      .mockResolvedValueOnce({ session_id: 'old-session' })
      .mockResolvedValueOnce({ session_id: 'new-session' });
    const onDraftReady = jest.fn();
    const onError = jest.fn();
    const onRewindRestart = jest.fn(() => {
      throw new Error('Analytics unavailable');
    });
    const runSession = jest.fn<
      ReturnType<ProfileOnboardingRunSession>,
      Parameters<ProfileOnboardingRunSession>
    >(({ sessionId, expectedTurnIndex, userInput, rewind, onMessage }) => {
      queueMicrotask(() => {
        if (rewind) {
          onMessage({
            type: 'error',
            content: 'transient_markdownflow_invalid',
          });
          return;
        }
        const fresh = sessionId === 'new-session';
        if (fresh && userInput) {
          onMessage({
            type: 'done',
            is_terminal: true,
            content: {
              done: true,
              input_accepted: true,
              next_turn_index: 2,
              pending_interaction_ids: [],
              profile_draft: 'Fresh profile draft',
            },
          });
          return;
        }
        const id = fresh ? 'fresh-goal' : userInput ? 'pace' : 'goal';
        onMessage({
          type: 'interaction',
          generated_block_bid: `${sessionId}-${id}`,
          interaction_id: id,
          content: `?[{{${id}}}...${id}]`,
        });
        onMessage({
          type: 'done',
          is_terminal: true,
          content: {
            done: false,
            input_accepted: Boolean(userInput),
            next_turn_index: expectedTurnIndex + 1,
            pending_interaction_ids: [id],
            rewindable_interaction_ids: userInput ? ['goal'] : [],
          },
        });
      });
      return { close: jest.fn() };
    });
    render(
      <Dialog open>
        <DialogContent aria-describedby={undefined}>
          <DialogTitle>{profileTitle}</DialogTitle>
          <ProfileOnboardingConversation
            createSession={createSession}
            runSession={runSession}
            onDraftReady={onDraftReady}
            onError={onError}
            onRewindRestart={onRewindRestart}
          />
        </DialogContent>
      </Dialog>,
    );
    const goal = await screen.findByPlaceholderText('goal');
    await user.type(goal, 'Original goal{Enter}');
    await screen.findByPlaceholderText('pace');
    await user.clear(goal);
    await user.type(goal, 'Edited goal{Enter}');
    await user.click(
      within(
        screen.getByRole('dialog', {
          name: 'module.chat.regenerateConfirmTitle',
        }),
      ).getByRole('button', { name: 'common.core.ok' }),
    );
    const freshGoal = await screen.findByPlaceholderText('fresh-goal');
    expect(freshGoal).toHaveValue('');
    expect(screen.queryByPlaceholderText('pace')).not.toBeInTheDocument();
    expect(mockToast).toHaveBeenCalledTimes(1);
    expect(mockToast).toHaveBeenCalledWith({
      title: 'module.profileOnboarding.guided.restartingAfterEditError',
    });
    expect(onRewindRestart).toHaveBeenCalledTimes(1);
    expect(createSession).toHaveBeenCalledTimes(2);
    expect(runSession).toHaveBeenLastCalledWith(
      expect.objectContaining({
        sessionId: 'new-session',
        expectedTurnIndex: 0,
        userInput: undefined,
      }),
    );
    expect(runSession.mock.calls.at(-1)?.[0]).not.toHaveProperty('rewind');
    expect(onError).not.toHaveBeenCalled();
    await user.type(freshGoal, 'Fresh goal{Enter}');
    await waitFor(() =>
      expect(onDraftReady).toHaveBeenCalledWith(
        'Fresh profile draft',
        'new-session',
      ),
    );
  },
);
