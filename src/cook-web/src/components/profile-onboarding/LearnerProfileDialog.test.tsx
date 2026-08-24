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
const FINISH_COLLECTION_LABEL = 'finish collection';
const FAIL_COLLECTION_LABEL = 'fail collection';
const RUN_COLLECTION_LABEL = 'run collection';
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
  deliverDraft: (draft?: string, nickname?: string) => void;
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
      deliverDraft: (draft = 'Collection draft', nickname?: string) => {
        if (mountedRef.current && sessionIdRef.current) {
          propsRef.current.onDraftReady(draft, sessionIdRef.current, nickname);
        }
      },
      deliverError: (error = new Error('Collection failed')) => {
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
      <output data-testid='mock-collection-session'>{sessionId}</output>
      <button
        type='button'
        disabled={!sessionId || props.disabled}
        onClick={() =>
          props.onDraftReady('Collection draft', sessionIdRef.current)
        }
      >
        {FINISH_COLLECTION_LABEL}
      </button>
      <button
        type='button'
        disabled={props.disabled}
        onClick={() => props.onError(new Error('Collection failed'))}
      >
        {FAIL_COLLECTION_LABEL}
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
        {RUN_COLLECTION_LABEL}
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
const SESSION_ID_2 = 'fedcba9876543210fedcba9876543210';

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
    exitPolicy: 'dismissible',
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
const informationUsageControl = () =>
  screen.getByTestId('learner-profile-information-usage');
const informationUsageSummary = () =>
  informationUsageControl().querySelector('summary') as HTMLElement;
const waitForCollectionSession = async (sessionId = SESSION_ID) => {
  await waitFor(() =>
    expect(screen.getByTestId('mock-collection-session')).toHaveTextContent(
      sessionId,
    ),
  );
};
const continueCollectionToSave = async () => {
  const button = await screen.findByRole('button', {
    name: 'module.profileOnboarding.guided.reviewCollection',
  });
  fireEvent.click(button);
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

  test('waits for profile and status before opening the compact collection phase', async () => {
    const profileRequest = deferred<typeof emptyProfile>();
    const statusRequest = deferred<ReturnType<typeof onboardingStatus>>();
    mockGetLearnerProfile.mockReturnValue(profileRequest.promise);
    mockGetProfileOnboardingV2.mockReturnValue(statusRequest.promise);

    renderDialog({ exitPolicy: 'blocking', presentation: 'blocking' });

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

    await waitForCollectionSession();
    expect(
      screen.queryByText('module.profileOnboarding.guided.title'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('module.profileOnboarding.guided.description'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText('module.profileOnboarding.dialog.unifiedDescription'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('learner-profile-dialog-body')).toHaveClass(
      'overflow-y-auto',
    );
    expect(
      screen.getByTestId('mock-profile-onboarding-conversation').parentElement,
    ).toHaveClass('min-h-40', '[@media(max-height:620px)]:min-h-32');
    expect(
      screen.getByTestId('learner-profile-dialog-footer'),
    ).toContainElement(informationUsageControl());
    expect(informationUsageControl()).not.toHaveAttribute('open');
    fireEvent.click(informationUsageSummary());
    expect(informationUsageControl()).toHaveAttribute('open');
    expect(
      await screen.findByText(
        'module.profileOnboarding.dialog.informationUsagePurpose',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'module.profileOnboarding.dialog.informationUsageSensitive',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'module.profileOnboarding.dialog.informationUsageEditable',
      ),
    ).toBeInTheDocument();
    fireEvent.click(informationUsageSummary());
    expect(informationUsageControl()).not.toHaveAttribute('open');
    expect(
      screen.queryByText('module.profileOnboarding.steps.collect'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('module.profileOnboarding.steps.review'),
    ).not.toBeInTheDocument();
  });

  test('shows an existing profile without waiting for optional onboarding status', async () => {
    const statusRequest = deferred<ReturnType<typeof onboardingStatus>>();
    mockGetLearnerProfile.mockResolvedValue(existingProfile);
    mockGetProfileOnboardingV2.mockReturnValue(statusRequest.promise);

    renderDialog();

    expect(
      await screen.findByDisplayValue(existingProfile.learner_profile),
    ).toBeInTheDocument();
    expect(profileInput()).toHaveAttribute(
      'placeholder',
      'module.profileOnboarding.profilePlaceholder',
    );
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
        exitPolicy='blocking'
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

    await waitForCollectionSession();
    rerender(
      <LearnerProfileDialog
        {...props}
        exitPolicy='blocking'
        presentation='blocking'
        initialOnboardingStatus={onboardingStatus()}
      />,
    );

    expect(screen.getByTestId('mock-collection-session')).toHaveTextContent(
      SESSION_ID,
    );
    expect(mockGetLearnerProfile).toHaveBeenCalledTimes(1);
    expect(mockGetProfileOnboardingV2).toHaveBeenCalledTimes(1);
    expect(mockCreateProfileOnboardingSession).toHaveBeenCalledTimes(1);
  });

  test('uses onboarding intent for a fresh profile and proxies runtime calls', async () => {
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingV2.mockResolvedValue(onboardingStatus());

    renderDialog({ exitPolicy: 'blocking', presentation: 'blocking' });

    await waitForCollectionSession();
    expect(mockCreateProfileOnboardingSession).toHaveBeenCalledWith(
      'en-US',
      'onboarding',
    );

    fireEvent.click(screen.getByRole('button', { name: 'run collection' }));
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

    renderDialog({ exitPolicy: 'dismissible' });

    await waitForCollectionSession();
    expect(mockCreateProfileOnboardingSession).toHaveBeenCalledWith(
      'en-US',
      'settings',
    );
    fireEvent.click(screen.getByRole('button', { name: 'finish collection' }));
    await continueCollectionToSave();
    await screen.findByDisplayValue('Collection draft');
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.complete',
      }),
    );
    await waitFor(() =>
      expect(mockCompleteGuidedProfileOnboarding).toHaveBeenCalledWith(
        expect.objectContaining({
          trigger_source: 'settings',
          session_id: SESSION_ID,
        }),
      ),
    );
  });

  test('opens an existing profile directly in the compact save phase', async () => {
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
    expect(
      screen.getByText('module.profileOnboarding.dialog.unifiedDescription'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('module.profileOnboarding.dialog.confirmDescription'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('module.profileOnboarding.dialog.promptHeading'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('learner-profile-guidance-identity'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('learner-profile-reassurance'),
    ).not.toBeInTheDocument();
    const interactiveCollectionButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.interactiveCollection',
    });
    const leftActions = screen.getByTestId(
      'learner-profile-dialog-left-actions',
    );
    expect(leftActions).toHaveClass('mr-auto', 'justify-start');
    expect(leftActions).toContainElement(informationUsageControl());
    expect(leftActions).toContainElement(interactiveCollectionButton);

    const saveActions = screen.getByTestId(
      'learner-profile-dialog-save-actions',
    );
    expect(saveActions).toHaveClass('w-full', 'sm:w-auto');
    expect(saveActions).not.toContainElement(interactiveCollectionButton);
    expect(saveActions).toContainElement(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.cancel',
      }),
    );
    expect(saveActions).toContainElement(saveButton());

    const optimizationCard = screen.getByTestId(
      'learner-profile-optimization-card',
    );
    expect(optimizationCard).toHaveClass(
      'rounded-xl',
      'border-primary/20',
      'bg-primary/[0.05]',
    );
    const optimizeButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.optimize',
    });
    expect(optimizationCard).toContainElement(optimizeButton);
    expect(optimizeButton).toHaveClass('bg-primary', 'shadow-sm');
    expect(
      screen.getByText('module.profileOnboarding.dialog.optimizeHint'),
    ).toBeInTheDocument();
  });

  test('cancels a clean dismissible save without persisting', async () => {
    const onClose = jest.fn();
    renderDialog({ onClose });
    await screen.findByDisplayValue(existingProfile.learner_profile);

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.cancel',
      }),
    );

    await waitFor(() => expect(onClose).toHaveBeenCalledWith('dismiss'));
    expect(mockUpdateLearnerProfile).not.toHaveBeenCalled();
    expect(mockCompleteGuidedProfileOnboarding).not.toHaveBeenCalled();
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
    expect(
      screen.queryByRole('button', {
        name: 'module.profileOnboarding.dialog.interactiveCollection',
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.cancel',
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.profileOnboarding.dialog.optimizeEmptyHint'),
    ).toBeInTheDocument();
  });

  test('waits for explicit review guidance before placing a terminal collection draft in the editor', async () => {
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingV2.mockResolvedValue(onboardingStatus());

    renderDialog({ exitPolicy: 'blocking', presentation: 'blocking' });
    await waitForCollectionSession();
    expect(screen.getByTestId('learner-profile-dialog-body')).toHaveClass(
      'overflow-y-auto',
    );
    fireEvent.click(screen.getByRole('button', { name: 'finish collection' }));

    expect(
      await screen.findByText(
        'module.profileOnboarding.guided.collectionComplete',
      ),
    ).toBeInTheDocument();
    const reviewButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.guided.reviewCollection',
    });
    expect(reviewButton).toHaveFocus();
    expect(
      screen.queryByLabelText('module.profileOnboarding.dialog.profileLabel'),
    ).not.toBeInTheDocument();
    expect(mockOptimizeLearnerProfile).not.toHaveBeenCalled();
    expect(mockCompleteGuidedProfileOnboarding).not.toHaveBeenCalled();
    expect(mockUpdateLearnerProfile).not.toHaveBeenCalled();

    fireEvent.click(reviewButton);
    expect(
      await screen.findByDisplayValue('Collection draft'),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByText('module.profileOnboarding.dialog.confirmTitle'),
      ).toHaveFocus(),
    );
    expect(
      screen.getByTestId('learner-profile-dialog-footer'),
    ).toContainElement(informationUsageControl());
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.optimize',
      }),
    ).toBeEnabled();
    expect(mockOptimizeLearnerProfile).not.toHaveBeenCalled();
    expect(mockCompleteGuidedProfileOnboarding).not.toHaveBeenCalled();
    expect(mockUpdateLearnerProfile).not.toHaveBeenCalled();
  });

  test('places an over-limit collection draft in the editor without invoking optimization', async () => {
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingV2.mockResolvedValue(onboardingStatus());

    renderDialog({ exitPolicy: 'blocking', presentation: 'blocking' });
    await waitForCollectionSession();
    act(() => {
      mockConversationControls.at(-1)?.deliverDraft('x'.repeat(1001));
    });
    await continueCollectionToSave();

    expect(
      await screen.findByDisplayValue('x'.repeat(1001)),
    ).toBeInTheDocument();
    expect(mockOptimizeLearnerProfile).not.toHaveBeenCalled();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.complete',
      }),
    ).toBeDisabled();
  });

  test('optimizes a collected draft only after an explicit request and can undo it', async () => {
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingV2.mockResolvedValue(onboardingStatus());

    renderDialog({ exitPolicy: 'dismissible' });
    await waitForCollectionSession();
    fireEvent.click(screen.getByRole('button', { name: 'finish collection' }));
    await continueCollectionToSave();

    expect(
      await screen.findByDisplayValue('Collection draft'),
    ).toBeInTheDocument();
    expect(mockOptimizeLearnerProfile).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.optimize',
      }),
    );
    expect(
      await screen.findByDisplayValue('Optimized learner introduction'),
    ).toBeInTheDocument();
    expect(mockOptimizeLearnerProfile).toHaveBeenCalledWith('Collection draft');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.undoOptimize',
      }),
    );
    expect(profileInput()).toHaveValue('Collection draft');
  });

  test('persists a guided result once with its session, trigger, and collected nickname', async () => {
    const onSaved = jest.fn();
    const onClose = jest.fn();
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingV2.mockResolvedValue(onboardingStatus());
    mockCompleteGuidedProfileOnboarding.mockResolvedValue({
      ...existingProfile,
      learner_profile: 'Collection draft',
      nickname: 'Taylor',
    });

    renderDialog({ exitPolicy: 'blocking', onSaved, onClose });
    await waitForCollectionSession();
    act(() => {
      mockConversationControls
        .at(-1)
        ?.deliverDraft('Collection draft', 'Taylor');
    });
    await continueCollectionToSave();
    await screen.findByDisplayValue('Collection draft');
    expect(nicknameInput()).toHaveValue('Taylor');
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.complete',
      }),
    );

    await waitFor(() =>
      expect(mockCompleteGuidedProfileOnboarding).toHaveBeenCalledWith({
        learner_profile: 'Collection draft',
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
      onClose.mock.invocationCallOrder[0],
    );
    expect(onClose.mock.invocationCallOrder[0]).toBeLessThan(
      onSaved.mock.invocationCallOrder[0],
    );
  });

  test('closes a durable save without waiting for the profile refresh', async () => {
    const refresh = deferred<void>();
    const onSaved = jest.fn(() => refresh.promise);
    const onClose = jest.fn();
    renderDialog({ exitPolicy: 'blocking', onSaved, onClose });
    await screen.findByDisplayValue(existingProfile.learner_profile);

    fireEvent.change(profileInput(), {
      target: { value: 'Saved before refresh' },
    });
    fireEvent.click(saveButton());

    await waitFor(() =>
      expect(mockUpdateLearnerProfile).toHaveBeenCalledWith(
        'Saved before refresh',
        undefined,
      ),
    );
    await waitFor(() => expect(onClose).toHaveBeenCalledWith('saved'));
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onClose.mock.invocationCallOrder[0]).toBeLessThan(
      onSaved.mock.invocationCallOrder[0],
    );
    expect(saveButton()).toBeEnabled();

    await act(async () => {
      refresh.resolve(undefined);
    });
  });

  test('omits an unchanged nickname from guided completion', async () => {
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingV2.mockResolvedValue(onboardingStatus());

    renderDialog({ exitPolicy: 'blocking' });
    await waitForCollectionSession();
    fireEvent.click(screen.getByRole('button', { name: 'finish collection' }));
    await continueCollectionToSave();
    await screen.findByDisplayValue('Collection draft');
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.complete',
      }),
    );

    await waitFor(() =>
      expect(mockCompleteGuidedProfileOnboarding).toHaveBeenCalledWith({
        learner_profile: 'Collection draft',
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
        learner_profile: 'Collection draft',
      });

    renderDialog({ exitPolicy: 'blocking' });
    await waitForCollectionSession();
    fireEvent.click(screen.getByRole('button', { name: 'finish collection' }));
    await continueCollectionToSave();
    await screen.findByDisplayValue('Collection draft');
    const complete = screen.getByRole('button', {
      name: 'module.profileOnboarding.complete',
    });
    fireEvent.click(complete);

    expect(await screen.findByText('Save unavailable')).toBeInTheDocument();
    expect(profileInput()).toHaveValue('Collection draft');
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
        name: 'module.profileOnboarding.dialog.interactiveCollection',
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
    expect(
      screen.getByTestId('learner-profile-dialog-footer'),
    ).toContainElement(informationUsageControl());
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
        name: 'module.profileOnboarding.dialog.interactiveCollection',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.replaceResearchConfirm',
      }),
    );

    await waitForCollectionSession();
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
        name: 'module.profileOnboarding.dialog.interactiveCollection',
      }),
    );
    await waitForCollectionSession();

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

  test('restores the prior collection completion context when a new collection is cancelled', async () => {
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingV2.mockResolvedValue(onboardingStatus());
    mockCreateProfileOnboardingSession
      .mockResolvedValueOnce(sessionResponse(SESSION_ID))
      .mockResolvedValueOnce(sessionResponse(SESSION_ID_2));

    renderDialog({ exitPolicy: 'dismissible' });
    await waitForCollectionSession(SESSION_ID);
    fireEvent.click(screen.getByRole('button', { name: 'finish collection' }));
    await continueCollectionToSave();
    await screen.findByDisplayValue('Collection draft');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.interactiveCollection',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.replaceResearchConfirm',
      }),
    );
    await waitForCollectionSession(SESSION_ID_2);
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.cancelResearch',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.complete',
      }),
    );

    await waitFor(() =>
      expect(mockCompleteGuidedProfileOnboarding).toHaveBeenCalledWith(
        expect.objectContaining({ session_id: SESSION_ID }),
      ),
    );
    expect(mockUpdateLearnerProfile).not.toHaveBeenCalled();
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

  test('does not report a blocking direct save as a settings action', async () => {
    renderDialog({ exitPolicy: 'blocking' });
    await screen.findByDisplayValue(existingProfile.learner_profile);

    const leftActions = screen.getByTestId(
      'learner-profile-dialog-left-actions',
    );
    expect(leftActions).toContainElement(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.interactiveCollection',
      }),
    );
    expect(leftActions).toContainElement(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.skip',
      }),
    );
    fireEvent.click(saveButton());

    await waitFor(() =>
      expect(mockUpdateLearnerProfile).toHaveBeenCalledWith(
        existingProfile.learner_profile,
        undefined,
      ),
    );
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      PROFILE_ONBOARDING_EVENTS.SETTINGS_SAVED,
    );
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      PROFILE_ONBOARDING_EVENTS.SETTINGS_CLEARED,
    );
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
    expect(
      screen.getByText('module.profileOnboarding.dialog.optimizeSuccess'),
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
      exitPolicy: 'blocking',
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
    expect(
      screen.queryByRole('button', {
        name: 'module.profileOnboarding.dialog.cancel',
      }),
    ).not.toBeInTheDocument();
    const leftActions = screen.getByTestId(
      'learner-profile-dialog-left-actions',
    );
    expect(leftActions).toContainElement(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.interactiveCollection',
      }),
    );
    expect(leftActions).toContainElement(
      screen.getByRole('button', { name: 'module.profileOnboarding.skip' }),
    );
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
      exitPolicy: 'blocking',
      presentation: 'blocking',
      externalErrorMessage: 'Skip unavailable',
      onClose,
      onDefer,
    });
    await waitForCollectionSession();

    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.skip' }),
    );
    await waitFor(() => expect(onDefer).toHaveBeenCalledWith(SESSION_ID));
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'finish collection' }));
    await continueCollectionToSave();
    expect(
      await screen.findByDisplayValue('Collection draft'),
    ).toBeInTheDocument();
    expect(mockOptimizeLearnerProfile).not.toHaveBeenCalled();
  });

  test('confirms before discarding dirty settings edits', async () => {
    const onClose = jest.fn();
    renderDialog({ onClose });
    await screen.findByDisplayValue(existingProfile.learner_profile);
    fireEvent.change(profileInput(), { target: { value: 'Unsaved edit' } });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.cancel',
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

    const { rerender, props } = renderDialog({ exitPolicy: 'blocking' });
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
