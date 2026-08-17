import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import {
  completeGuidedProfileOnboarding,
  createProfileOnboardingSession,
  getLearnerProfile,
  getProfileOnboardingV2,
  optimizeLearnerProfile,
  runProfileOnboardingSession,
  type ProfileOnboardingV2Status,
  updateLearnerProfile,
} from '@/api/learnerProfile';
import { PROFILE_ONBOARDING_EVENTS } from './events';
import LearnerProfileDialog from './LearnerProfileDialog';
import type { ProfileOnboardingConversationProps } from './ProfileOnboardingConversation';

const mockToast = jest.fn();
const mockTrackEvent = jest.fn();
let mockLanguage = 'en-US';
const FINISH_RESEARCH_LABEL = 'finish research';
const FAIL_RESEARCH_LABEL = 'fail research';
const RUN_RESEARCH_LABEL = 'run research';
const RETRY_CONVERSATION_LABEL = 'retry conversation';

const translateKey = (
  key: string,
  params?: Record<string, string | number>,
) => {
  if (key === 'module.profileOnboarding.characterCount') {
    return `${params?.count} / ${params?.max}`;
  }
  if (key === 'module.profileOnboarding.characterCountOverLimit') {
    return `${params?.count} / ${params?.max} over limit`;
  }
  return key;
};

type ConversationControl = {
  deliverDraft: (draft?: string) => void;
  deliverError: (error?: Error) => void;
  sessionId: () => string;
};

const mockConversationControls: ConversationControl[] = [];

function MockProfileOnboardingConversation(
  props: ProfileOnboardingConversationProps,
) {
  const propsRef = React.useRef(props);
  const mountedRef = React.useRef(true);
  const sessionIdRef = React.useRef('');
  const [sessionId, setSessionId] = React.useState('');
  const { createSession } = props;
  propsRef.current = props;

  React.useEffect(() => {
    mountedRef.current = true;
    const control: ConversationControl = {
      deliverDraft: (draft = 'Research draft') => {
        if (mountedRef.current && sessionIdRef.current) {
          propsRef.current.onDraftReady(draft, sessionIdRef.current);
        }
      },
      deliverError: (error = new Error('Research failed')) => {
        if (mountedRef.current) {
          propsRef.current.onError(error);
        }
      },
      sessionId: () => sessionIdRef.current,
    };
    mockConversationControls.push(control);

    return () => {
      mountedRef.current = false;
    };
  }, []);

  React.useEffect(() => {
    let active = true;
    void createSession()
      .then(session => {
        if (!active || !mountedRef.current) {
          return;
        }
        sessionIdRef.current = session.session_id;
        setSessionId(session.session_id);
        propsRef.current.onSessionStarted?.(session.session_id);
      })
      .catch(error => {
        if (active && mountedRef.current) {
          propsRef.current.onError(error);
        }
      });

    return () => {
      active = false;
    };
  }, [createSession]);

  return (
    <div data-testid='mock-profile-onboarding-conversation'>
      <output data-testid='mock-research-session'>{sessionId}</output>
      <button
        type='button'
        disabled={!sessionId || props.disabled}
        onClick={() =>
          props.onDraftReady('Research draft', sessionIdRef.current)
        }
      >
        {FINISH_RESEARCH_LABEL}
      </button>
      <button
        type='button'
        disabled={props.disabled}
        onClick={() => props.onError(new Error('Research failed'))}
      >
        {FAIL_RESEARCH_LABEL}
      </button>
      <button
        type='button'
        disabled={!sessionId || props.disabled}
        onClick={() =>
          props.runSession({
            sessionId,
            expectedBlockIndex: 1,
            requestId: 'request-1',
            userInput: { answer: ['value'] },
            onMessage: jest.fn(),
            onError: jest.fn(),
          })
        }
      >
        {RUN_RESEARCH_LABEL}
      </button>
      <button
        type='button'
        onClick={() => props.onRetry?.()}
      >
        {RETRY_CONVERSATION_LABEL}
      </button>
      {props.errorMessage ? <p>{props.errorMessage}</p> : null}
    </div>
  );
}

jest.mock('@/api/learnerProfile', () => ({
  completeGuidedProfileOnboarding: jest.fn(),
  createProfileOnboardingSession: jest.fn(),
  getLearnerProfile: jest.fn(),
  getProfileOnboardingV2: jest.fn(),
  isProfileOnboardingV2Status: (value: unknown) =>
    typeof value === 'object' &&
    value !== null &&
    'contract_version' in value &&
    value.contract_version === 'profile-v2',
  optimizeLearnerProfile: jest.fn(),
  runProfileOnboardingSession: jest.fn(),
  updateLearnerProfile: jest.fn(),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('./ProfileOnboardingConversation', () => ({
  __esModule: true,
  default: (props: ProfileOnboardingConversationProps) => (
    <MockProfileOnboardingConversation {...props} />
  ),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: translateKey,
    i18n: {
      language: mockLanguage,
      resolvedLanguage: mockLanguage,
    },
  }),
}));

const mockCompleteGuidedProfileOnboarding =
  completeGuidedProfileOnboarding as jest.Mock;
const mockCreateProfileOnboardingSession =
  createProfileOnboardingSession as jest.Mock;
const mockGetLearnerProfile = getLearnerProfile as jest.Mock;
const mockGetProfileOnboardingV2 = getProfileOnboardingV2 as jest.Mock;
const mockOptimizeLearnerProfile = optimizeLearnerProfile as jest.Mock;
const mockRunProfileOnboardingSession =
  runProfileOnboardingSession as jest.Mock;
const mockUpdateLearnerProfile = updateLearnerProfile as jest.Mock;

const SESSION_ID = '0123456789abcdef0123456789abcdef';

const existingProfile = {
  learner_profile: 'Existing learner introduction',
  learner_profile_updated_at: '2026-08-11T01:00:00Z',
  has_learner_profile: true,
  max_length: 1000,
  nickname: 'Alex',
  nickname_max_length: 64,
};

const emptyProfile = {
  learner_profile: '',
  learner_profile_updated_at: null,
  has_learner_profile: false,
  max_length: 1000,
  nickname: '',
  nickname_max_length: 64,
};

const onboardingStatus = (
  overrides: Record<string, unknown> = {},
): ProfileOnboardingV2Status =>
  ({
    contract_version: 'profile-v2',
    enabled: true,
    guided_available: true,
    should_show: true,
    presentation: 'blocking',
    handled: false,
    legacy_handled: false,
    ...emptyProfile,
    ...overrides,
  }) as ProfileOnboardingV2Status;

const sessionResponse = (sessionId = SESSION_ID) => ({
  session_id: sessionId,
  block_index: 0,
  block_count: 2,
  profile_draft_block_index: 1,
  done: false,
  expires_in: 900,
});

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
};

const renderDialog = (
  overrides: Partial<React.ComponentProps<typeof LearnerProfileDialog>> = {},
) => {
  const props: React.ComponentProps<typeof LearnerProfileDialog> = {
    open: true,
    mode: 'settings',
    draftStorageScope: 'user-a',
    onClose: jest.fn(),
    ...overrides,
  };
  return { props, ...render(<LearnerProfileDialog {...props} />) };
};

const profileInput = () =>
  screen.getByLabelText('module.profileOnboarding.dialog.profileLabel');
const nicknameInput = () =>
  screen.getByLabelText('module.profileOnboarding.dialog.nicknameLabel');
const saveButton = () =>
  screen.getByRole('button', {
    name: 'module.profileOnboarding.dialog.saveChanges',
  });
const waitForResearchSession = async (sessionId = SESSION_ID) => {
  await waitFor(() =>
    expect(screen.getByTestId('mock-research-session')).toHaveTextContent(
      sessionId,
    ),
  );
};

describe('LearnerProfileDialog', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockConversationControls.splice(0);
    mockLanguage = 'en-US';
    mockGetLearnerProfile.mockResolvedValue(existingProfile);
    mockGetProfileOnboardingV2.mockResolvedValue(
      onboardingStatus({
        should_show: false,
        presentation: 'hidden',
        handled: true,
        ...existingProfile,
      }),
    );
    mockCreateProfileOnboardingSession.mockResolvedValue(sessionResponse());
    mockCompleteGuidedProfileOnboarding.mockResolvedValue(existingProfile);
    mockUpdateLearnerProfile.mockResolvedValue(existingProfile);
    mockOptimizeLearnerProfile.mockResolvedValue({
      optimized_learner_profile: 'Optimized learner introduction',
    });
    mockRunProfileOnboardingSession.mockReturnValue({ close: jest.fn() });
  });

  test('waits for both profile and onboarding status before choosing research', async () => {
    const profileRequest = deferred<typeof emptyProfile>();
    const statusRequest = deferred<ReturnType<typeof onboardingStatus>>();
    mockGetLearnerProfile.mockReturnValue(profileRequest.promise);
    mockGetProfileOnboardingV2.mockReturnValue(statusRequest.promise);

    renderDialog({ mode: 'onboarding', presentation: 'blocking' });

    expect(
      screen.getByText('module.profileOnboarding.dialog.loading'),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('mock-profile-onboarding-conversation'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText('module.profileOnboarding.dialog.profileLabel'),
    ).not.toBeInTheDocument();

    await act(async () => {
      statusRequest.resolve(onboardingStatus());
    });
    expect(
      screen.getByText('module.profileOnboarding.dialog.loading'),
    ).toBeInTheDocument();
    expect(mockCreateProfileOnboardingSession).not.toHaveBeenCalled();

    await act(async () => {
      profileRequest.resolve(emptyProfile);
    });

    expect(
      await screen.findByText('module.profileOnboarding.guided.title'),
    ).toBeInTheDocument();
    await waitForResearchSession();
  });

  test('shows an existing profile without waiting for optional onboarding status', async () => {
    const statusRequest = deferred<ReturnType<typeof onboardingStatus>>();
    mockGetLearnerProfile.mockResolvedValue(existingProfile);
    mockGetProfileOnboardingV2.mockReturnValue(statusRequest.promise);

    renderDialog();

    expect(
      await screen.findByDisplayValue(existingProfile.learner_profile),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('module.profileOnboarding.dialog.loading'),
    ).not.toBeInTheDocument();
    expect(mockCreateProfileOnboardingSession).not.toHaveBeenCalled();

    await act(async () => {
      statusRequest.resolve(
        onboardingStatus({ handled: true, ...existingProfile }),
      );
    });
    expect(profileInput()).toHaveValue(existingProfile.learner_profile);
  });

  test('keeps the same draft and load when the host upgrades the open dialog to onboarding', async () => {
    const { rerender, props } = renderDialog();

    await screen.findByDisplayValue(existingProfile.learner_profile);
    fireEvent.change(profileInput(), {
      target: { value: 'Unsaved profile from the menu entry' },
    });
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.close',
      }),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.close',
      }),
    );
    expect(
      screen.getByText('module.profileOnboarding.dialog.discardTitle'),
    ).toBeInTheDocument();

    rerender(
      <LearnerProfileDialog
        {...props}
        mode='onboarding'
        presentation='blocking'
        initialOnboardingStatus={onboardingStatus()}
      />,
    );

    expect(profileInput()).toHaveValue('Unsaved profile from the menu entry');
    expect(mockGetLearnerProfile).toHaveBeenCalledTimes(1);
    expect(mockGetProfileOnboardingV2).toHaveBeenCalledTimes(1);
    expect(
      screen.queryByText('module.profileOnboarding.dialog.discardTitle'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', {
        name: 'module.profileOnboarding.dialog.close',
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.skip',
      }),
    ).toBeInTheDocument();
  });

  test('keeps an active research session when the host upgrades the open dialog to onboarding', async () => {
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingV2.mockResolvedValue(onboardingStatus());
    const { rerender, props } = renderDialog();

    await waitForResearchSession();
    rerender(
      <LearnerProfileDialog
        {...props}
        mode='onboarding'
        presentation='blocking'
        initialOnboardingStatus={onboardingStatus()}
      />,
    );

    expect(screen.getByTestId('mock-research-session')).toHaveTextContent(
      SESSION_ID,
    );
    expect(mockGetLearnerProfile).toHaveBeenCalledTimes(1);
    expect(mockGetProfileOnboardingV2).toHaveBeenCalledTimes(1);
    expect(mockCreateProfileOnboardingSession).toHaveBeenCalledTimes(1);
  });

  test('uses onboarding intent for a fresh profile and proxies runtime calls', async () => {
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingV2.mockResolvedValue(onboardingStatus());

    renderDialog({ mode: 'onboarding', presentation: 'blocking' });

    await waitForResearchSession();
    expect(mockCreateProfileOnboardingSession).toHaveBeenCalledWith(
      'en-US',
      'onboarding',
    );

    fireEvent.click(screen.getByRole('button', { name: 'run research' }));
    expect(mockRunProfileOnboardingSession).toHaveBeenCalledWith(
      expect.objectContaining({
        sessionId: SESSION_ID,
        expectedBlockIndex: 1,
        requestId: 'request-1',
        userInput: { answer: ['value'] },
        language: 'en-US',
      }),
    );
  });

  test('uses settings intent for a handled learner without a profile', async () => {
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingV2.mockResolvedValue(
      onboardingStatus({ handled: true, should_show: false }),
    );

    renderDialog({ mode: 'settings' });

    await waitForResearchSession();
    expect(mockCreateProfileOnboardingSession).toHaveBeenCalledWith(
      'en-US',
      'settings',
    );
  });

  test('opens an existing profile directly in review without a false step indicator or rewrite', async () => {
    renderDialog();

    expect(
      await screen.findByDisplayValue(existingProfile.learner_profile),
    ).toBeInTheDocument();
    expect(nicknameInput()).toHaveValue('Alex');
    expect(mockCreateProfileOnboardingSession).not.toHaveBeenCalled();
    expect(mockOptimizeLearnerProfile).not.toHaveBeenCalled();
    expect(screen.getByTestId('learner-profile-dialog-body')).toHaveClass(
      'overflow-y-auto',
    );
    expect(screen.getByTestId('learner-profile-dialog-footer')).toHaveClass(
      'shrink-0',
    );
    expect(
      screen.queryByText('module.profileOnboarding.steps.collect'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('module.profileOnboarding.steps.review'),
    ).not.toBeInTheDocument();
  });

  test('falls back to a manual empty editor when guided research is unavailable', async () => {
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingV2.mockResolvedValue(
      onboardingStatus({ enabled: false, guided_available: false }),
    );

    renderDialog();

    expect(
      await screen.findByText('module.profileOnboarding.dialog.manualFallback'),
    ).toBeInTheDocument();
    expect(profileInput()).toHaveValue('');
    expect(mockCreateProfileOnboardingSession).not.toHaveBeenCalled();
  });

  test('auto-optimizes a terminal research draft without persisting early', async () => {
    const optimization = deferred<{ optimized_learner_profile: string }>();
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingV2.mockResolvedValue(onboardingStatus());
    mockOptimizeLearnerProfile.mockReturnValue(optimization.promise);

    renderDialog({ mode: 'onboarding', presentation: 'blocking' });
    await waitForResearchSession();
    expect(screen.getByTestId('learner-profile-dialog-body')).toHaveClass(
      'overflow-hidden',
    );
    fireEvent.click(screen.getByRole('button', { name: 'finish research' }));

    const optimizingHeading = await screen.findByText(
      'module.profileOnboarding.dialog.autoOptimizing',
    );
    await waitFor(() => expect(optimizingHeading).toHaveFocus());
    expect(mockOptimizeLearnerProfile).toHaveBeenCalledWith('Research draft');
    expect(mockCompleteGuidedProfileOnboarding).not.toHaveBeenCalled();
    expect(mockUpdateLearnerProfile).not.toHaveBeenCalled();

    await act(async () => {
      optimization.resolve({
        optimized_learner_profile: 'Optimized research draft',
      });
    });

    expect(
      await screen.findByDisplayValue('Optimized research draft'),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByText('module.profileOnboarding.dialog.confirmTitle'),
      ).toHaveFocus(),
    );
    expect(
      screen.getByText('module.profileOnboarding.steps.review'),
    ).toBeInTheDocument();
    expect(mockCompleteGuidedProfileOnboarding).not.toHaveBeenCalled();
  });

  test('keeps the research draft savable after automatic optimization fails and can retry', async () => {
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingV2.mockResolvedValue(onboardingStatus());
    mockOptimizeLearnerProfile
      .mockRejectedValueOnce(new Error('Optimizer unavailable'))
      .mockResolvedValueOnce({ optimized_learner_profile: 'Retried draft' });

    renderDialog({ mode: 'onboarding' });
    await waitForResearchSession();
    fireEvent.click(screen.getByRole('button', { name: 'finish research' }));

    expect(
      await screen.findByDisplayValue('Research draft'),
    ).toBeInTheDocument();
    expect(screen.getByText('Optimizer unavailable')).toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.useResearchDraft',
      }),
    ).toBeEnabled();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.retryOptimize',
      }),
    );
    expect(
      await screen.findByDisplayValue('Retried draft'),
    ).toBeInTheDocument();
  });

  test('can directly restore the raw research draft after successful optimization', async () => {
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingV2.mockResolvedValue(onboardingStatus());

    renderDialog({ mode: 'onboarding' });
    await waitForResearchSession();
    fireEvent.click(screen.getByRole('button', { name: 'finish research' }));
    expect(
      await screen.findByDisplayValue('Optimized learner introduction'),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.useResearchDraft',
      }),
    );
    expect(profileInput()).toHaveValue('Research draft');
  });

  test('persists a guided result once with its session, trigger, and changed nickname', async () => {
    const onSaved = jest.fn();
    const onClose = jest.fn();
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingV2.mockResolvedValue(onboardingStatus());
    mockCompleteGuidedProfileOnboarding.mockResolvedValue({
      ...existingProfile,
      learner_profile: 'Optimized learner introduction',
      nickname: 'Taylor',
    });

    renderDialog({ mode: 'onboarding', onSaved, onClose });
    await waitForResearchSession();
    fireEvent.click(screen.getByRole('button', { name: 'finish research' }));
    await screen.findByDisplayValue('Optimized learner introduction');
    fireEvent.change(nicknameInput(), { target: { value: ' Taylor ' } });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.complete',
      }),
    );

    await waitFor(() =>
      expect(mockCompleteGuidedProfileOnboarding).toHaveBeenCalledWith({
        learner_profile: 'Optimized learner introduction',
        trigger_source: 'guided',
        session_id: SESSION_ID,
        nickname: 'Taylor',
      }),
    );
    expect(mockCompleteGuidedProfileOnboarding).toHaveBeenCalledTimes(1);
    expect(mockUpdateLearnerProfile).not.toHaveBeenCalled();
    await waitFor(() => expect(onClose).toHaveBeenCalledWith('saved'));
    expect(onSaved).toHaveBeenCalledTimes(1);
    const completedCall = mockTrackEvent.mock.calls.findIndex(
      ([event]) => event === PROFILE_ONBOARDING_EVENTS.COMPLETED,
    );
    expect(mockTrackEvent.mock.invocationCallOrder[completedCall]).toBeLessThan(
      onSaved.mock.invocationCallOrder[0],
    );
  });

  test('omits an unchanged nickname from guided completion', async () => {
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingV2.mockResolvedValue(onboardingStatus());

    renderDialog({ mode: 'onboarding' });
    await waitForResearchSession();
    fireEvent.click(screen.getByRole('button', { name: 'finish research' }));
    await screen.findByDisplayValue('Optimized learner introduction');
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.complete',
      }),
    );

    await waitFor(() =>
      expect(mockCompleteGuidedProfileOnboarding).toHaveBeenCalledWith({
        learner_profile: 'Optimized learner introduction',
        trigger_source: 'guided',
        session_id: SESSION_ID,
      }),
    );
  });

  test('keeps the guided session and draft after save failure so save can retry', async () => {
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingV2.mockResolvedValue(onboardingStatus());
    mockCompleteGuidedProfileOnboarding
      .mockRejectedValueOnce(new Error('Save unavailable'))
      .mockResolvedValueOnce({
        ...existingProfile,
        learner_profile: 'Optimized learner introduction',
      });

    renderDialog({ mode: 'onboarding' });
    await waitForResearchSession();
    fireEvent.click(screen.getByRole('button', { name: 'finish research' }));
    await screen.findByDisplayValue('Optimized learner introduction');
    const complete = screen.getByRole('button', {
      name: 'module.profileOnboarding.complete',
    });
    fireEvent.click(complete);

    expect(await screen.findByText('Save unavailable')).toBeInTheDocument();
    expect(profileInput()).toHaveValue('Optimized learner introduction');
    fireEvent.click(complete);

    await waitFor(() =>
      expect(mockCompleteGuidedProfileOnboarding).toHaveBeenCalledTimes(2),
    );
    expect(mockCompleteGuidedProfileOnboarding.mock.calls[1][0]).toEqual(
      mockCompleteGuidedProfileOnboarding.mock.calls[0][0],
    );
  });

  test('asks before replacing a dirty draft and starts settings research only after confirmation', async () => {
    renderDialog();
    await screen.findByDisplayValue(existingProfile.learner_profile);
    fireEvent.change(profileInput(), { target: { value: 'Unsaved edit' } });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.settings.rerun',
      }),
    );
    expect(
      await screen.findByText(
        'module.profileOnboarding.dialog.replaceResearchTitle',
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
    await waitFor(() =>
      expect(
        screen.getByText(
          'module.profileOnboarding.dialog.replaceResearchTitle',
        ),
      ).toHaveFocus(),
    );
    expect(mockCreateProfileOnboardingSession).not.toHaveBeenCalled();
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      PROFILE_ONBOARDING_EVENTS.SETTINGS_RERUN_STARTED,
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.keepEditing',
      }),
    );
    expect(profileInput()).toHaveValue('Unsaved edit');
    await waitFor(() =>
      expect(
        screen.getByText('module.profileOnboarding.dialog.confirmTitle'),
      ).toHaveFocus(),
    );
    expect(mockCreateProfileOnboardingSession).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.settings.rerun',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.replaceResearchConfirm',
      }),
    );

    await waitForResearchSession();
    expect(mockCreateProfileOnboardingSession).toHaveBeenCalledWith(
      'en-US',
      'settings',
    );
    expect(mockTrackEvent).toHaveBeenCalledWith(
      PROFILE_ONBOARDING_EVENTS.SETTINGS_RERUN_STARTED,
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.cancelResearch',
      }),
    );
    expect(await screen.findByDisplayValue('Unsaved edit')).toBeInTheDocument();
    expect(mockCompleteGuidedProfileOnboarding).not.toHaveBeenCalled();
    expect(mockUpdateLearnerProfile).not.toHaveBeenCalled();
  });

  test('cancels settings research back to the untouched local draft without skip or persistence', async () => {
    renderDialog();
    await screen.findByDisplayValue(existingProfile.learner_profile);
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.settings.rerun',
      }),
    );
    await waitForResearchSession();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.cancelResearch',
      }),
    );

    expect(
      await screen.findByDisplayValue(existingProfile.learner_profile),
    ).toBeInTheDocument();
    expect(mockCompleteGuidedProfileOnboarding).not.toHaveBeenCalled();
    expect(mockUpdateLearnerProfile).not.toHaveBeenCalled();
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      PROFILE_ONBOARDING_EVENTS.SKIPPED,
      expect.anything(),
    );
  });

  test('directly edits profile and nickname through the canonical PUT path', async () => {
    mockUpdateLearnerProfile.mockResolvedValue({
      ...existingProfile,
      learner_profile: 'Direct edit',
      nickname: 'Morgan',
    });
    const onSaved = jest.fn();
    renderDialog({ onSaved });
    await screen.findByDisplayValue(existingProfile.learner_profile);

    fireEvent.change(profileInput(), { target: { value: ' Direct edit ' } });
    fireEvent.change(nicknameInput(), { target: { value: 'Morgan' } });
    fireEvent.click(saveButton());

    await waitFor(() =>
      expect(mockUpdateLearnerProfile).toHaveBeenCalledWith(
        'Direct edit',
        'Morgan',
      ),
    );
    expect(mockCompleteGuidedProfileOnboarding).not.toHaveBeenCalled();
    expect(onSaved).toHaveBeenCalledTimes(1);
  });

  test('preserves an unchanged nickname when directly clearing the profile', async () => {
    mockUpdateLearnerProfile.mockResolvedValue({
      ...existingProfile,
      learner_profile: '',
      has_learner_profile: false,
    });
    renderDialog();
    await screen.findByDisplayValue(existingProfile.learner_profile);

    fireEvent.change(profileInput(), { target: { value: '' } });
    fireEvent.click(saveButton());

    await waitFor(() =>
      expect(mockUpdateLearnerProfile).toHaveBeenCalledWith('', undefined),
    );
  });

  test('migrates a displayed legacy nickname without putting legacy fields in the editor', async () => {
    mockGetLearnerProfile.mockResolvedValue({
      ...existingProfile,
      nickname: '',
      legacy_profile_values: {
        sys_user_nickname: 'Legacy name',
        sys_user_background: 'Legacy background',
        sys_user_style: 'Legacy style',
      },
    });
    renderDialog();

    expect(await screen.findByDisplayValue('Legacy name')).toBeInTheDocument();
    expect(profileInput()).toHaveValue(existingProfile.learner_profile);
    expect(profileInput().textContent).not.toContain('sys_user_');
    fireEvent.click(saveButton());
    await waitFor(() =>
      expect(mockUpdateLearnerProfile).toHaveBeenCalledWith(
        existingProfile.learner_profile,
        'Legacy name',
      ),
    );
  });

  test('optimizes a direct edit in place and lets the learner undo it', async () => {
    renderDialog();
    await screen.findByDisplayValue(existingProfile.learner_profile);
    fireEvent.change(profileInput(), { target: { value: 'Draft to improve' } });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.optimize',
      }),
    );
    expect(
      await screen.findByDisplayValue('Optimized learner introduction'),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.undoOptimize',
      }),
    );
    expect(profileInput()).toHaveValue('Draft to improve');
  });

  test('keeps a direct draft savable after optimization fails', async () => {
    mockOptimizeLearnerProfile.mockRejectedValue(
      new Error('Moderation rejected this draft'),
    );
    renderDialog();
    await screen.findByDisplayValue(existingProfile.learner_profile);
    fireEvent.change(profileInput(), { target: { value: 'Safe draft' } });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.optimize',
      }),
    );

    expect(
      await screen.findByText('Moderation rejected this draft'),
    ).toBeInTheDocument();
    expect(profileInput()).toHaveValue('Safe draft');
    expect(saveButton()).toBeEnabled();
  });

  test('blocks implicit dismissal during onboarding and defers only through the explicit action', async () => {
    const onClose = jest.fn();
    const onDefer = jest.fn().mockResolvedValue(true);
    renderDialog({
      mode: 'onboarding',
      presentation: 'blocking',
      onClose,
      onDefer,
    });
    await screen.findByDisplayValue(existingProfile.learner_profile);

    expect(
      screen.queryByRole('button', {
        name: 'module.profileOnboarding.dialog.close',
      }),
    ).not.toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape', code: 'Escape' });
    fireEvent.pointerDown(document.body);
    fireEvent.click(document.body);
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.skip' }),
    );
    await waitFor(() => expect(onDefer).toHaveBeenCalledWith(undefined));
    const skippedCall = mockTrackEvent.mock.calls.findIndex(
      ([event]) => event === PROFILE_ONBOARDING_EVENTS.SKIPPED,
    );
    expect(mockTrackEvent.mock.invocationCallOrder[skippedCall]).toBeLessThan(
      onClose.mock.invocationCallOrder[0],
    );
    expect(onClose).toHaveBeenCalledWith('dismiss');
  });

  test('keeps research usable when explicit defer fails', async () => {
    const onClose = jest.fn();
    const onDefer = jest.fn().mockResolvedValue(false);
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingV2.mockResolvedValue(onboardingStatus());
    renderDialog({
      mode: 'onboarding',
      presentation: 'blocking',
      externalErrorMessage: 'Skip unavailable',
      onClose,
      onDefer,
    });
    await waitForResearchSession();

    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.skip' }),
    );
    await waitFor(() => expect(onDefer).toHaveBeenCalledWith(SESSION_ID));
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'finish research' }));
    expect(
      await screen.findByDisplayValue('Optimized learner introduction'),
    ).toBeInTheDocument();
  });

  test('keeps automatic optimization running when explicit defer fails', async () => {
    const optimization = deferred<{ optimized_learner_profile: string }>();
    const onDefer = jest.fn().mockResolvedValue(false);
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingV2.mockResolvedValue(onboardingStatus());
    mockOptimizeLearnerProfile.mockReturnValue(optimization.promise);
    renderDialog({
      mode: 'onboarding',
      presentation: 'blocking',
      externalErrorMessage: 'Skip unavailable',
      onDefer,
    });
    await waitForResearchSession();
    fireEvent.click(screen.getByRole('button', { name: 'finish research' }));
    await screen.findByText('module.profileOnboarding.dialog.autoOptimizing');

    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.skip' }),
    );
    await waitFor(() => expect(onDefer).toHaveBeenCalledWith(SESSION_ID));
    expect(screen.getByText('Skip unavailable')).toBeInTheDocument();

    await act(async () => {
      optimization.resolve({
        optimized_learner_profile: 'Optimized after failed defer',
      });
    });
    expect(
      await screen.findByDisplayValue('Optimized after failed defer'),
    ).toBeInTheDocument();
  });

  test('confirms before discarding dirty settings edits', async () => {
    const onClose = jest.fn();
    renderDialog({ onClose });
    await screen.findByDisplayValue(existingProfile.learner_profile);
    fireEvent.change(profileInput(), { target: { value: 'Unsaved edit' } });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.close',
      }),
    );
    expect(
      await screen.findByText('module.profileOnboarding.dialog.discardTitle'),
    ).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.discard',
      }),
    );
    await waitFor(() => expect(onClose).toHaveBeenCalledWith('dismiss'));
  });

  test('ignores late research session and draft delivery after an account switch', async () => {
    const firstSession = deferred<ReturnType<typeof sessionResponse>>();
    mockGetLearnerProfile
      .mockResolvedValueOnce(emptyProfile)
      .mockResolvedValueOnce({
        ...existingProfile,
        learner_profile: 'Account B profile',
        nickname: 'Blake',
      });
    mockGetProfileOnboardingV2
      .mockResolvedValueOnce(onboardingStatus())
      .mockResolvedValueOnce(
        onboardingStatus({
          handled: true,
          should_show: false,
          presentation: 'hidden',
          ...existingProfile,
          learner_profile: 'Account B profile',
          nickname: 'Blake',
        }),
      );
    mockCreateProfileOnboardingSession.mockReturnValue(firstSession.promise);

    const { rerender, props } = renderDialog({ mode: 'onboarding' });
    await screen.findByTestId('mock-profile-onboarding-conversation');
    const accountAControl = mockConversationControls.at(-1)!;

    rerender(
      <LearnerProfileDialog
        {...props}
        draftStorageScope='user-b'
      />,
    );
    expect(
      await screen.findByDisplayValue('Account B profile'),
    ).toBeInTheDocument();

    await act(async () => {
      firstSession.resolve(sessionResponse());
    });
    act(() => accountAControl.deliverDraft('Stale account A draft'));

    expect(profileInput()).toHaveValue('Account B profile');
    expect(mockOptimizeLearnerProfile).not.toHaveBeenCalledWith(
      'Stale account A draft',
    );
    expect(mockCompleteGuidedProfileOnboarding).not.toHaveBeenCalled();
  });

  test('ignores late optimization and save results after an account switch', async () => {
    const optimization = deferred<{ optimized_learner_profile: string }>();
    const save = deferred<typeof existingProfile>();
    mockGetLearnerProfile
      .mockResolvedValueOnce(existingProfile)
      .mockResolvedValue({
        ...existingProfile,
        learner_profile: 'Account B profile',
        nickname: 'Blake',
      });
    mockGetProfileOnboardingV2.mockResolvedValue(
      onboardingStatus({ handled: true, ...existingProfile }),
    );
    mockOptimizeLearnerProfile.mockReturnValue(optimization.promise);
    mockUpdateLearnerProfile.mockReturnValue(save.promise);
    const onClose = jest.fn();
    const onSaved = jest.fn();
    const { rerender, props } = renderDialog({ onClose, onSaved });
    await screen.findByDisplayValue(existingProfile.learner_profile);

    fireEvent.change(profileInput(), { target: { value: 'Account A edit' } });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.optimize',
      }),
    );
    rerender(
      <LearnerProfileDialog
        {...props}
        draftStorageScope='user-b'
      />,
    );
    await screen.findByDisplayValue('Account B profile');
    await act(async () => {
      optimization.resolve({ optimized_learner_profile: 'Stale optimization' });
    });
    expect(profileInput()).toHaveValue('Account B profile');

    fireEvent.change(profileInput(), { target: { value: 'Account B edit' } });
    fireEvent.click(saveButton());
    rerender(
      <LearnerProfileDialog
        {...props}
        draftStorageScope='user-c'
      />,
    );
    await act(async () => {
      save.resolve({
        ...existingProfile,
        learner_profile: 'Late saved Account B edit',
      });
    });
    expect(onSaved).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });
});
