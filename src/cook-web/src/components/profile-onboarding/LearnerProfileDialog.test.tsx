import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import {
  completeGuidedProfileOnboarding,
  createProfileOnboardingSession,
  getLearnerProfile,
  getProfileOnboarding,
  optimizeLearnerProfile,
  runProfileOnboardingSession,
  type ProfileOnboardingStatus,
  updateLearnerProfile,
} from '@/api/learnerProfile';
import { PROFILE_ONBOARDING_EVENTS } from './events';
import LearnerProfileDialog from './LearnerProfileDialog';
import type { ProfileOnboardingConversationProps } from './ProfileOnboardingConversation';

const mockToast = jest.fn();
const mockTrackEvent = jest.fn();
let mockTrackEventIdentity = mockTrackEvent;
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

const expectSafeRetentionAnalyticsPayload = (payload: unknown) => {
  const record = payload as Record<string, unknown>;
  expect(Object.keys(record).sort()).toEqual([
    'phase',
    'presentation',
    'source',
  ]);
  for (const prohibitedField of [
    'dialog_session_id',
    'learner_profile',
    'nickname',
    'question',
    'session_id',
    'slide_body',
  ]) {
    expect(record).not.toHaveProperty(prohibitedField);
  }
};

type ConversationControl = {
  deliverDraft: (draft?: string, nickname?: string) => void;
  deliverError: (error?: Error) => void;
  deliverAssistantDraft: (draft: string, nickname?: string) => void;
  changeAssistantDraft: (draft: string) => void;
  assistantDraft: () => string | undefined;
  setRunInFlight: (runInFlight: boolean) => void;
  sessionId: () => string;
};

const mockConversationControls: ConversationControl[] = [];
const mockAssistantDraftRenders: Array<{
  value: string | undefined;
  change: ProfileOnboardingConversationProps['onAssistantDraftChange'];
}> = [];

function MockProfileOnboardingConversation(
  props: ProfileOnboardingConversationProps,
) {
  // Capture render-time props, including the account-switch render before
  // passive effects restore the next account's draft.
  mockAssistantDraftRenders.push({
    value: props.assistantDraft,
    change: props.onAssistantDraftChange,
  });
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
      deliverAssistantDraft: (draft, nickname) =>
        propsRef.current.onAssistantDraftReady?.(
          draft,
          sessionIdRef.current,
          nickname,
        ),
      changeAssistantDraft: draft =>
        propsRef.current.onAssistantDraftChange?.(draft),
      assistantDraft: () => propsRef.current.assistantDraft,
      deliverError: (error = new Error('Collection failed')) => {
        if (mountedRef.current) {
          propsRef.current.onError(error);
        }
      },
      setRunInFlight: (runInFlight: boolean) => {
        if (mountedRef.current) {
          propsRef.current.onRunInFlightChange?.(runInFlight);
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
          if ((error as { code?: unknown }).code === 2001) {
            propsRef.current.onSessionCreateRejected?.(error);
          } else {
            propsRef.current.onError(error);
          }
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
      {props.questionScrollFooter}
    </div>
  );
}

jest.mock('@/api/learnerProfile', () => ({
  completeGuidedProfileOnboarding: jest.fn(),
  createProfileOnboardingSession: jest.fn(),
  getLearnerProfile: jest.fn(),
  getProfileOnboarding: jest.fn(),
  isProfileOnboardingStatus: (value: unknown) =>
    typeof value === 'object' &&
    value !== null &&
    'guided_available' in value &&
    'presentation' in value,
  optimizeLearnerProfile: jest.fn(),
  runProfileOnboardingSession: jest.fn(),
  updateLearnerProfile: jest.fn(),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEventIdentity }),
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
const mockGetProfileOnboardingStatus = getProfileOnboarding as jest.Mock;
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
): ProfileOnboardingStatus =>
  ({
    enabled: true,
    guided_available: true,
    should_show: true,
    presentation: 'blocking',
    handled: false,
    ...emptyProfile,
    ...overrides,
  }) as ProfileOnboardingStatus;

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
    autoStartCollection: true,
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
const informationUsageControl = (variant: 'inline' | 'popover') =>
  screen.getByTestId(`learner-profile-information-usage-${variant}`);
const informationUsageSummary = (variant: 'inline' | 'popover') =>
  informationUsageControl(variant).querySelector('summary') as HTMLElement;
const interactiveCollectionButton = (
  placement: 'mobile' | 'desktop' = 'mobile',
) => screen.getByTestId(`learner-profile-interactive-collection-${placement}`);
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
    window.sessionStorage.clear();
    mockConversationControls.splice(0);
    mockAssistantDraftRenders.splice(0);
    mockLanguage = 'en-US';
    mockTrackEventIdentity = mockTrackEvent;
    mockGetLearnerProfile.mockResolvedValue(existingProfile);
    mockGetProfileOnboardingStatus.mockResolvedValue(
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
    mockGetProfileOnboardingStatus.mockReturnValue(statusRequest.promise);

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
    expect(screen.getByRole('dialog')).toHaveClass(
      'outline-none',
      'focus:outline-none',
      'focus-within:outline-none',
      'focus-within:ring-0',
    );
    expect(screen.getByTestId('learner-profile-dialog-content')).toHaveClass(
      'inset-0',
      'h-dvh',
      'w-screen',
      'rounded-none',
      'border-0',
      'sm:inset-auto',
      'sm:left-1/2',
      'sm:top-1/2',
      'sm:h-[min(88dvh,760px)]',
      'sm:w-[calc(100vw-48px)]',
      'sm:max-w-[900px]',
      'sm:-translate-x-1/2',
      'sm:-translate-y-1/2',
      'sm:rounded-2xl',
      'sm:border',
      'max-sm:[&_input]:min-h-11',
      'max-sm:[&_select]:min-h-11',
      'sm:any-pointer-coarse:[&_button]:min-h-11',
      'sm:any-pointer-coarse:[&_button]:min-w-11',
      'sm:any-pointer-coarse:[&_input]:min-h-11',
      'sm:any-pointer-coarse:[&_input]:text-base',
      'sm:any-pointer-coarse:[&_select]:min-h-11',
      'sm:any-pointer-coarse:[&_select]:text-base',
      'sm:any-pointer-coarse:[&_textarea]:text-base',
    );
    expect(
      screen.queryByTestId('learner-profile-mobile-handle'),
    ).not.toBeInTheDocument();
    expect(
      screen
        .getByTestId('learner-profile-dialog-content')
        .querySelector('header'),
    ).toHaveClass(
      'pl-[max(1rem,env(safe-area-inset-left,0px))]',
      'pr-[max(1rem,env(safe-area-inset-right,0px))]',
      'pt-[max(0.75rem,env(safe-area-inset-top,0px))]',
      '[@media(max-height:620px)]:pt-[max(0.75rem,env(safe-area-inset-top,0px))]',
    );
    expect(
      screen.getByText('module.profileOnboarding.dialog.unifiedTitle'),
    ).toHaveClass(
      '[@media(max-height:620px)]:text-xl',
      '[@media(max-height:620px)]:leading-7',
    );
    expect(
      screen.getByText('module.profileOnboarding.dialog.unifiedDescription'),
    ).toHaveClass(
      '[@media(max-height:620px)]:text-sm',
      '[@media(max-height:620px)]:leading-5',
    );
    expect(screen.getByTestId('learner-profile-dialog-header')).toHaveClass(
      'border-b',
      'after:-bottom-6',
      'after:h-6',
      'after:bg-background/55',
      'after:backdrop-blur-md',
    );
    expect(screen.getByTestId('learner-profile-dialog-body')).toHaveClass(
      'overflow-hidden',
      'bg-muted/25',
      'pb-[var(--learner-profile-footer-height,80px)]',
      'pt-[var(--learner-profile-header-height,96px)]',
      'sm:pb-[var(--learner-profile-footer-height,76px)]',
      'sm:pt-[var(--learner-profile-header-height,116px)]',
    );
    expect(screen.getByTestId('learner-profile-dialog-body')).not.toHaveClass(
      'overflow-y-auto',
    );
    expect(
      screen.getByTestId('mock-profile-onboarding-conversation').parentElement,
    ).toHaveClass('min-h-0', 'flex-1');
    expect(
      screen.getByTestId('mock-profile-onboarding-conversation').parentElement,
    ).not.toHaveClass('min-h-40');
    expect(screen.getByTestId('learner-profile-dialog-footer')).toHaveClass(
      'absolute',
      'bottom-0',
      'z-10',
      'pb-[max(0.75rem,env(safe-area-inset-bottom,0px))]',
      '[@media(max-height:620px)]:flex-nowrap',
      '[@media(max-height:620px)]:pb-[max(0.75rem,env(safe-area-inset-bottom,0px))]',
      '[@media(max-height:620px)]:pt-3',
      'border-t',
      'bg-background/90',
      'backdrop-blur-xl',
      'before:-top-6',
      'before:h-6',
      'before:bg-background/55',
      'before:backdrop-blur-md',
    );
    const inlineInformation = informationUsageControl('inline');
    const popoverInformation = informationUsageControl('popover');
    expect(
      screen.getByTestId('learner-profile-dialog-footer'),
    ).toContainElement(popoverInformation);
    expect(popoverInformation).toHaveClass(
      'hidden',
      'sm:block',
      '[@media(max-height:620px)]:hidden',
    );
    expect(
      screen.getByTestId('mock-profile-onboarding-conversation'),
    ).toContainElement(inlineInformation);
    expect(inlineInformation).toHaveClass(
      'sm:hidden',
      '[@media(max-height:620px)]:block',
    );
    expect(inlineInformation).not.toHaveAttribute('open');
    expect(inlineInformation.querySelector('[role="note"]')).not.toHaveClass(
      'absolute',
    );
    expect(popoverInformation.querySelector('[role="note"]')).toHaveClass(
      'absolute',
    );
    fireEvent.click(informationUsageSummary('inline'));
    expect(inlineInformation).toHaveAttribute('open');
    expect(
      await within(inlineInformation).findByText(
        'module.profileOnboarding.dialog.informationUsagePurpose',
      ),
    ).toBeInTheDocument();
    expect(
      within(inlineInformation).getByText(
        'module.profileOnboarding.dialog.informationUsageSensitive',
      ),
    ).toBeInTheDocument();
    expect(
      within(inlineInformation).getByText(
        'module.profileOnboarding.dialog.informationUsageEditable',
      ),
    ).toBeInTheDocument();
    fireEvent.click(informationUsageSummary('inline'));
    expect(inlineInformation).not.toHaveAttribute('open');
    expect(
      screen.queryByText('module.profileOnboarding.steps.collect'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('module.profileOnboarding.steps.review'),
    ).not.toBeInTheDocument();
  });

  test('shows retention instead of a second-step footer while profile data is loading', async () => {
    const profileRequest = deferred<typeof emptyProfile>();
    const statusRequest = deferred<ReturnType<typeof onboardingStatus>>();
    const onDefer = jest.fn().mockResolvedValue(true);
    mockGetLearnerProfile.mockReturnValue(profileRequest.promise);
    mockGetProfileOnboardingStatus.mockReturnValue(statusRequest.promise);

    renderDialog({
      exitPolicy: 'blocking',
      presentation: 'blocking',
      onDefer,
    });
    expect(
      screen.getByText('module.profileOnboarding.dialog.loading'),
    ).toBeInTheDocument();

    const initialSkipButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.skip',
    });
    fireEvent.click(initialSkipButton);
    fireEvent.click(initialSkipButton);
    expect(
      await screen.findByText(
        'module.profileOnboarding.dialog.retention.title',
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('module.profileOnboarding.dialog.loading'),
    ).not.toBeInTheDocument();
    expect(onDefer).not.toHaveBeenCalled();

    await act(async () => {
      statusRequest.resolve(onboardingStatus());
      profileRequest.resolve(emptyProfile);
    });
    await waitForCollectionSession();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.retention.continueSetup',
      }),
    );
    expect(
      screen.getByTestId('mock-profile-onboarding-conversation'),
    ).toBeVisible();
  });

  test('keeps a load failure retry available after returning from retention', async () => {
    const onDefer = jest.fn().mockResolvedValue(true);
    mockGetLearnerProfile
      .mockRejectedValueOnce(new Error('Profile unavailable'))
      .mockResolvedValueOnce(existingProfile);

    renderDialog({
      exitPolicy: 'blocking',
      presentation: 'blocking',
      onDefer,
    });

    expect(await screen.findByText('Profile unavailable')).toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.retry',
      }),
    ).toBeEnabled();

    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.skip' }),
    );
    expect(
      await screen.findByText(
        'module.profileOnboarding.dialog.retention.title',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText('Profile unavailable')).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.retention.continueSetup',
      }),
    );
    expect(await screen.findByText('Profile unavailable')).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.retry',
      }),
    );
    expect(
      await screen.findByDisplayValue(existingProfile.learner_profile),
    ).toBeInTheDocument();
    expect(mockGetLearnerProfile).toHaveBeenCalledTimes(2);
    expect(onDefer).not.toHaveBeenCalled();
  });

  test('measures dialog chrome after a closed dialog opens even when loading fails', async () => {
    const originalResizeObserver = globalThis.ResizeObserver;
    const observe = jest.fn();
    const disconnect = jest.fn();
    const resizeObserver = {
      disconnect,
      observe,
      unobserve: jest.fn(),
    } as unknown as ResizeObserver;
    let resizeCallback: ResizeObserverCallback | undefined;
    const ResizeObserverMock = jest.fn((callback: ResizeObserverCallback) => {
      resizeCallback = callback;
      return resizeObserver;
    });
    Object.defineProperty(globalThis, 'ResizeObserver', {
      configurable: true,
      value: ResizeObserverMock,
    });
    mockGetLearnerProfile.mockRejectedValueOnce(
      new Error('Profile unavailable'),
    );

    try {
      const { props, rerender } = renderDialog({ open: false });
      expect(ResizeObserverMock).not.toHaveBeenCalled();

      rerender(
        <LearnerProfileDialog
          {...props}
          open
        />,
      );

      expect(
        await screen.findByText('Profile unavailable'),
      ).toBeInTheDocument();
      const header = screen.getByTestId('learner-profile-dialog-header');
      const footer = screen.getByTestId('learner-profile-dialog-footer');
      jest
        .spyOn(header, 'getBoundingClientRect')
        .mockReturnValue({ height: 104 } as DOMRect);
      jest
        .spyOn(footer, 'getBoundingClientRect')
        .mockReturnValue({ height: 72 } as DOMRect);

      await waitFor(() => {
        expect(observe).toHaveBeenCalledWith(header);
        expect(observe).toHaveBeenCalledWith(footer);
      });
      act(() => resizeCallback?.([], resizeObserver));

      expect(screen.getByTestId('learner-profile-dialog-body')).toHaveStyle({
        '--learner-profile-footer-height': '72px',
        '--learner-profile-header-height': '104px',
      });
    } finally {
      if (originalResizeObserver) {
        Object.defineProperty(globalThis, 'ResizeObserver', {
          configurable: true,
          value: originalResizeObserver,
        });
      } else {
        Reflect.deleteProperty(globalThis, 'ResizeObserver');
      }
    }
  });

  test('shows an existing profile without waiting for optional onboarding status', async () => {
    const statusRequest = deferred<ReturnType<typeof onboardingStatus>>();
    mockGetLearnerProfile.mockResolvedValue(existingProfile);
    mockGetProfileOnboardingStatus.mockReturnValue(statusRequest.promise);

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

  test('keeps an empty profile in the editor outside the course onboarding gate', async () => {
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingStatus.mockResolvedValue(onboardingStatus());

    renderDialog({ autoStartCollection: false });

    expect(
      await screen.findByLabelText(
        'module.profileOnboarding.dialog.profileLabel',
      ),
    ).toHaveValue('');
    expect(
      screen.queryByTestId('mock-profile-onboarding-conversation'),
    ).not.toBeInTheDocument();
    expect(interactiveCollectionButton()).toBeInTheDocument();
    expect(mockCreateProfileOnboardingSession).not.toHaveBeenCalled();
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
    expect(mockGetProfileOnboardingStatus).toHaveBeenCalledTimes(1);
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
    mockGetProfileOnboardingStatus.mockResolvedValue(onboardingStatus());
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
    expect(mockGetProfileOnboardingStatus).toHaveBeenCalledTimes(1);
    expect(mockCreateProfileOnboardingSession).toHaveBeenCalledTimes(1);
  });

  test('uses onboarding intent for a fresh profile and proxies runtime calls', async () => {
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingStatus.mockResolvedValue(onboardingStatus());

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
    mockGetProfileOnboardingStatus.mockResolvedValue(
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
      'pb-[calc(var(--learner-profile-footer-height,80px)+1.5rem)]',
      'pt-[calc(var(--learner-profile-header-height,96px)+1.5rem)]',
    );
    expect(screen.getByTestId('learner-profile-dialog-footer')).toHaveClass(
      'absolute',
      'bottom-0',
    );
    expect(screen.getByTestId('learner-profile-save-view')).toHaveClass(
      'flex',
      'min-h-full',
      'flex-1',
      'flex-col',
    );
    expect(profileInput().parentElement).toHaveClass(
      'min-h-48',
      'flex-1',
      'sm:min-h-40',
      '[@media(max-height:620px)]:min-h-40',
    );
    expect(nicknameInput()).toHaveClass(
      'h-11',
      'text-base',
      'sm:h-10',
      'sm:text-sm',
    );
    expect(profileInput()).toHaveClass(
      'min-h-40',
      'flex-1',
      'resize-none',
      'text-base',
      'sm:min-h-32',
      'sm:text-sm',
      '[@media(max-height:620px)]:min-h-32',
    );
    expect(profileInput().closest('section')).toHaveClass(
      'min-h-60',
      'flex-1',
      'sm:min-h-52',
      '[@media(max-height:620px)]:min-h-52',
      '[@media(max-height:620px)]:flex-none',
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
    const mobileCollectionButton = interactiveCollectionButton('mobile');
    const desktopCollectionButton = interactiveCollectionButton('desktop');
    const leftActions = screen.getByTestId(
      'learner-profile-dialog-left-actions',
    );
    expect(leftActions).toHaveClass('me-auto', 'justify-start');
    expect(leftActions).toContainElement(informationUsageControl('popover'));
    expect(leftActions).toContainElement(desktopCollectionButton);
    expect(desktopCollectionButton).toHaveClass(
      'hidden',
      'sm:inline-flex',
      '[@media(max-height:620px)]:hidden',
    );
    expect(screen.getByTestId('learner-profile-save-view')).toContainElement(
      informationUsageControl('inline'),
    );
    expect(screen.getByTestId('learner-profile-save-view')).toContainElement(
      mobileCollectionButton,
    );
    expect(screen.getByTestId('learner-profile-save-heading-row')).toHaveClass(
      'flex',
      'items-center',
      'justify-between',
      'sm:block',
      '[@media(max-height:620px)]:flex',
    );
    expect(
      screen.getByTestId('learner-profile-save-heading-row'),
    ).toContainElement(mobileCollectionButton);
    expect(mobileCollectionButton).toHaveClass(
      'min-h-11',
      'w-fit',
      'max-w-[48%]',
      'shrink-0',
      'justify-start',
      'sm:hidden',
      '[@media(max-height:620px)]:inline-flex',
    );
    expect(mobileCollectionButton).not.toHaveClass(
      'w-full',
      'border-input',
      'bg-background',
    );
    expect(mobileCollectionButton).toHaveAccessibleName(
      'module.profileOnboarding.dialog.interactiveCollection',
    );
    expect(mobileCollectionButton.querySelector('svg')).toHaveAttribute(
      'aria-hidden',
      'true',
    );
    expect(informationUsageControl('inline')).toHaveClass(
      '[@media(max-height:620px)]:block',
    );

    const saveActions = screen.getByTestId(
      'learner-profile-dialog-save-actions',
    );
    expect(saveActions).toHaveClass('flex-1', 'sm:w-auto', 'sm:flex-none');
    expect(saveActions).not.toContainElement(mobileCollectionButton);
    expect(saveActions).not.toContainElement(desktopCollectionButton);
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
      'shrink-0',
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

  test('scrolls a focused form control into the nearest visible position', async () => {
    const scrollIntoView = jest.fn();
    const originalScrollIntoView = HTMLElement.prototype.scrollIntoView;
    const originalRequestAnimationFrame = window.requestAnimationFrame;
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: scrollIntoView,
    });
    Object.defineProperty(window, 'requestAnimationFrame', {
      configurable: true,
      value: undefined,
    });

    try {
      renderDialog();
      await screen.findByDisplayValue(existingProfile.learner_profile);
      fireEvent.focus(nicknameInput());

      expect(scrollIntoView).toHaveBeenCalledWith({
        block: 'nearest',
        inline: 'nearest',
      });
    } finally {
      Object.defineProperty(window, 'requestAnimationFrame', {
        configurable: true,
        value: originalRequestAnimationFrame,
      });
      if (originalScrollIntoView) {
        Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
          configurable: true,
          value: originalScrollIntoView,
        });
      } else {
        Reflect.deleteProperty(HTMLElement.prototype, 'scrollIntoView');
      }
    }
  });

  test('offers review after an existing profile starts collection from the menu flow', async () => {
    renderDialog({ autoStartCollection: false });

    await screen.findByDisplayValue(existingProfile.learner_profile);
    fireEvent.click(interactiveCollectionButton());
    await waitForCollectionSession();
    expect(mockCreateProfileOnboardingSession).toHaveBeenCalledWith(
      'en-US',
      'settings',
    );
    expect(
      screen.getByTestId('learner-profile-dialog-footer'),
    ).toContainElement(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.cancelResearch',
      }),
    );

    fireEvent.click(screen.getByRole('button', { name: 'finish collection' }));
    const reviewButton = await screen.findByRole('button', {
      name: 'module.profileOnboarding.guided.reviewCollection',
    });
    const compactCancelButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.cancelResearch',
    });
    expect(reviewButton).toHaveFocus();
    expect(compactCancelButton).toHaveClass(
      'sm:hidden',
      '[@media(max-height:620px)]:inline-flex',
    );
    expect(
      screen.getByTestId('learner-profile-dialog-footer'),
    ).toContainElement(compactCancelButton);

    fireEvent.click(reviewButton);
    expect(
      await screen.findByDisplayValue('Collection draft'),
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
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      PROFILE_ONBOARDING_EVENTS.RETENTION_SHOWN,
      expect.anything(),
    );
  });

  test('preserves the paste on ordinary settings close and restores it on same-account reopen', async () => {
    const onClose = jest.fn();
    const { rerender, props } = renderDialog({ onClose });
    await screen.findByDisplayValue(existingProfile.learner_profile);
    fireEvent.click(interactiveCollectionButton());
    await waitForCollectionSession();
    act(() =>
      mockConversationControls
        .at(-1)
        ?.changeAssistantDraft('Keep this paste for later'),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.close',
      }),
    );
    await waitFor(() => expect(onClose).toHaveBeenCalledWith('dismiss'));
    expect(
      screen.queryByText('module.profileOnboarding.dialog.discardTitle'),
    ).not.toBeInTheDocument();
    expect(
      window.sessionStorage.getItem(
        'profile-onboarding-paste-draft:profile-v2:user-a',
      ),
    ).toBe('Keep this paste for later');
    rerender(
      <LearnerProfileDialog
        {...props}
        open={false}
      />,
    );
    rerender(
      <LearnerProfileDialog
        {...props}
        open
      />,
    );
    await screen.findByDisplayValue(existingProfile.learner_profile);
    fireEvent.click(interactiveCollectionButton());
    await waitForCollectionSession();
    expect(mockConversationControls.at(-1)?.assistantDraft()).toBe(
      'Keep this paste for later',
    );
    expect(mockCompleteGuidedProfileOnboarding).not.toHaveBeenCalled();
  });

  test('falls back to a manual empty editor when guided research is unavailable', async () => {
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingStatus.mockResolvedValue(
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

  test('refreshes eligibility after the backend rejects session creation', async () => {
    const rejection = Object.assign(new Error('parameter error: intent'), {
      code: 2001,
      status: 200,
    });
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingStatus
      .mockResolvedValueOnce(onboardingStatus())
      .mockResolvedValueOnce(
        onboardingStatus({
          enabled: false,
          guided_available: false,
          should_show: false,
          presentation: 'hidden',
        }),
      );
    mockCreateProfileOnboardingSession.mockRejectedValue(rejection);

    renderDialog({ exitPolicy: 'blocking' });

    expect(
      await screen.findByLabelText(
        'module.profileOnboarding.dialog.profileLabel',
      ),
    ).toHaveValue('');
    expect(mockGetProfileOnboardingStatus).toHaveBeenCalledTimes(2);
    expect(
      screen.queryByTestId('mock-profile-onboarding-conversation'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText('module.profileOnboarding.dialog.manualFallback'),
    ).toBeInTheDocument();
  });

  test('waits for explicit review guidance before placing a terminal collection draft in the editor', async () => {
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingStatus.mockResolvedValue(onboardingStatus());

    renderDialog({ exitPolicy: 'blocking', presentation: 'blocking' });
    await waitForCollectionSession();
    expect(screen.getByTestId('learner-profile-dialog-body')).toHaveClass(
      'overflow-hidden',
    );
    fireEvent.click(screen.getByRole('button', { name: 'finish collection' }));

    expect(
      await screen.findByText(
        'module.profileOnboarding.guided.collectionComplete',
      ),
    ).toHaveClass('shrink-0');
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
    expect(screen.getByTestId('learner-profile-dialog-body')).toHaveClass(
      'overflow-y-auto',
    );
    await waitFor(() =>
      expect(
        screen.getByText('module.profileOnboarding.dialog.confirmTitle'),
      ).toHaveFocus(),
    );
    expect(
      screen.getByTestId('learner-profile-dialog-footer'),
    ).toContainElement(informationUsageControl('popover'));
    expect(informationUsageControl('popover')).toHaveClass(
      '[@media(max-height:620px)]:hidden',
    );
    expect(screen.getByTestId('learner-profile-dialog-body')).toContainElement(
      informationUsageControl('inline'),
    );
    expect(informationUsageControl('inline')).toHaveClass(
      '[@media(max-height:620px)]:block',
    );
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
    mockGetProfileOnboardingStatus.mockResolvedValue(onboardingStatus());

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
    mockGetProfileOnboardingStatus.mockResolvedValue(onboardingStatus());

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

  test('assistant nickname-only result opens confirmation without optimizing or saving and preserves the changed nickname payload', async () => {
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingStatus.mockResolvedValue(onboardingStatus());
    mockCompleteGuidedProfileOnboarding.mockResolvedValue({
      ...emptyProfile,
      nickname: 'Robin',
    });
    renderDialog({ exitPolicy: 'blocking' });
    await waitForCollectionSession();
    act(() =>
      mockConversationControls.at(-1)?.changeAssistantDraft('Call me Robin'),
    );
    act(() =>
      mockConversationControls.at(-1)?.deliverAssistantDraft('', 'Robin'),
    );
    expect(
      await screen.findByLabelText(
        'module.profileOnboarding.dialog.nicknameLabel',
      ),
    ).toHaveValue('Robin');
    expect(profileInput()).toHaveValue('');
    expect(mockOptimizeLearnerProfile).not.toHaveBeenCalled();
    expect(mockCompleteGuidedProfileOnboarding).not.toHaveBeenCalled();
    expect(mockUpdateLearnerProfile).not.toHaveBeenCalled();
    expect(
      window.sessionStorage.getItem(
        'profile-onboarding-paste-draft:profile-v2:user-a',
      ),
    ).toBe('Call me Robin');
    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.complete' }),
    );
    await waitFor(() =>
      expect(mockCompleteGuidedProfileOnboarding).toHaveBeenCalledWith({
        learner_profile: '',
        nickname: 'Robin',
        trigger_source: 'guided',
        session_id: SESSION_ID,
      }),
    );
    await waitFor(() =>
      expect(
        window.sessionStorage.getItem(
          'profile-onboarding-paste-draft:profile-v2:user-a',
        ),
      ).toBeNull(),
    );
  });

  test('restores the same account paste without submitting and clears the previous account even when the dialog is closed', async () => {
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingStatus.mockResolvedValue(onboardingStatus());
    window.sessionStorage.setItem(
      'profile-onboarding-paste-draft:profile-v2:user-a',
      'Restored private draft',
    );
    window.sessionStorage.setItem(
      'profile-onboarding-paste-draft:active-user:profile-v2',
      'profile-onboarding-paste-draft:profile-v2:user-a',
    );
    const { rerender, props } = renderDialog({ exitPolicy: 'blocking' });
    await waitForCollectionSession();
    expect(mockConversationControls.at(-1)?.assistantDraft()).toBe(
      'Restored private draft',
    );
    expect(mockCompleteGuidedProfileOnboarding).not.toHaveBeenCalled();
    rerender(
      <LearnerProfileDialog
        {...props}
        open={false}
        draftStorageScope='user-b'
      />,
    );
    expect(
      window.sessionStorage.getItem(
        'profile-onboarding-paste-draft:profile-v2:user-a',
      ),
    ).toBeNull();
  });

  test('never renders the previous account paste during a switch and rejects its stale change callback', async () => {
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingStatus.mockResolvedValue(onboardingStatus());
    window.sessionStorage.setItem(
      'profile-onboarding-paste-draft:profile-v2:user-b',
      'Private account B draft',
    );
    const { rerender, props } = renderDialog({ exitPolicy: 'blocking' });
    await waitForCollectionSession();
    act(() =>
      mockConversationControls
        .at(-1)
        ?.changeAssistantDraft('Private account A draft'),
    );
    const priorRender = mockAssistantDraftRenders.at(-1);
    expect(priorRender?.value).toBe('Private account A draft');
    const transitionRenderIndex = mockAssistantDraftRenders.length;

    rerender(
      <LearnerProfileDialog
        {...props}
        draftStorageScope='user-b'
      />,
    );
    // This is the first render of the still-mounted conversation, before
    // useEffect resets the old collection or restores account B's draft.
    expect(mockAssistantDraftRenders[transitionRenderIndex]?.value).toBe('');
    expect(
      mockAssistantDraftRenders
        .slice(transitionRenderIndex)
        .map(rendered => rendered.value),
    ).not.toContain('Private account A draft');
    await waitForCollectionSession();
    expect(mockConversationControls.at(-1)?.assistantDraft()).toBe(
      'Private account B draft',
    );

    act(() => priorRender?.change?.('Delayed account A update'));
    expect(mockConversationControls.at(-1)?.assistantDraft()).toBe(
      'Private account B draft',
    );
    expect(
      window.sessionStorage.getItem(
        'profile-onboarding-paste-draft:profile-v2:user-a',
      ),
    ).toBeNull();
    expect(
      window.sessionStorage.getItem(
        'profile-onboarding-paste-draft:profile-v2:user-b',
      ),
    ).toBe('Private account B draft');
  });

  test('persists a guided result once with its session, trigger, and collected nickname', async () => {
    const onSaved = jest.fn();
    const onClose = jest.fn();
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingStatus.mockResolvedValue(onboardingStatus());
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
    mockGetProfileOnboardingStatus.mockResolvedValue(onboardingStatus());

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
    mockGetProfileOnboardingStatus.mockResolvedValue(onboardingStatus());
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

    fireEvent.click(interactiveCollectionButton());
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
    ).toContainElement(informationUsageControl('popover'));
    expect(informationUsageControl('popover').parentElement).toHaveClass(
      '[@media(max-height:620px)]:hidden',
    );
    expect(screen.getByTestId('learner-profile-dialog-body')).toContainElement(
      informationUsageControl('inline'),
    );
    expect(informationUsageControl('inline')).toHaveClass(
      '[@media(max-height:620px)]:block',
    );
    expect(
      screen.getByTestId('learner-profile-confirmation-replace-collection'),
    ).toHaveClass(
      'justify-start',
      'sm:justify-center',
      '[@media(max-height:620px)]:justify-start',
    );
    expect(screen.getByTestId('learner-profile-dialog-body')).toHaveClass(
      'overflow-y-auto',
    );
    const confirmationActions = screen.getByTestId(
      'learner-profile-dialog-confirmation-actions',
    );
    expect(confirmationActions).toHaveClass('w-full', 'sm:w-auto');
    expect(confirmationActions).toContainElement(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.keepEditing',
      }),
    );
    expect(confirmationActions).toContainElement(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.replaceResearchConfirm',
      }),
    );
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

    fireEvent.click(interactiveCollectionButton());
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
    fireEvent.click(interactiveCollectionButton());
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
    mockGetProfileOnboardingStatus.mockResolvedValue(onboardingStatus());
    mockCreateProfileOnboardingSession
      .mockResolvedValueOnce(sessionResponse(SESSION_ID))
      .mockResolvedValueOnce(sessionResponse(SESSION_ID_2));

    renderDialog({ exitPolicy: 'dismissible' });
    await waitForCollectionSession(SESSION_ID);
    fireEvent.click(screen.getByRole('button', { name: 'finish collection' }));
    await continueCollectionToSave();
    await screen.findByDisplayValue('Collection draft');

    fireEvent.click(interactiveCollectionButton());
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
      interactiveCollectionButton('desktop'),
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

  test('opens retention first and defers only after final confirmation', async () => {
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
      interactiveCollectionButton('desktop'),
    );
    expect(leftActions).toContainElement(
      screen.getByRole('button', { name: 'module.profileOnboarding.skip' }),
    );
    fireEvent.keyDown(document, { key: 'Escape', code: 'Escape' });
    fireEvent.pointerDown(document.body);
    fireEvent.click(document.body);
    expect(onClose).not.toHaveBeenCalled();

    const originalProfileInput = profileInput();
    const originalNicknameInput = nicknameInput();
    const dialogContent = screen.getByTestId('learner-profile-dialog-content');
    fireEvent.change(originalProfileInput, {
      target: { value: 'Draft kept through retention' },
    });
    fireEvent.change(originalNicknameInput, {
      target: { value: 'Taylor' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.skip' }),
    );

    const retentionHeading = await screen.findByText(
      'module.profileOnboarding.dialog.retention.title',
    );
    await waitFor(() => expect(retentionHeading).toHaveFocus());
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
    expect(screen.getByTestId('learner-profile-dialog-content')).toBe(
      dialogContent,
    );
    expect(dialogContent).toHaveClass(
      'sm:h-[min(88dvh,760px)]',
      'sm:max-w-[900px]',
    );
    expect(dialogContent).not.toHaveClass('sm:!h-[min(94dvh,1072px)]');
    expect(dialogContent).not.toHaveClass('sm:!max-w-[1344px]');
    expect(onDefer).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      PROFILE_ONBOARDING_EVENTS.SKIPPED,
      expect.anything(),
    );
    expect(mockTrackEvent).toHaveBeenCalledWith(
      PROFILE_ONBOARDING_EVENTS.RETENTION_SHOWN,
      {
        source: 'guided',
        presentation: 'blocking',
        phase: 'save',
      },
    );
    const retentionShownPayload = mockTrackEvent.mock.calls.find(
      ([event]) => event === PROFILE_ONBOARDING_EVENTS.RETENTION_SHOWN,
    )?.[1];
    expectSafeRetentionAnalyticsPayload(retentionShownPayload);
    expect(
      mockTrackEvent.mock.calls.filter(
        ([event]) => event === PROFILE_ONBOARDING_EVENTS.RETENTION_SHOWN,
      ),
    ).toHaveLength(1);

    const continueSetupButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.retention.continueSetup',
    });
    fireEvent.click(continueSetupButton);
    fireEvent.click(continueSetupButton);
    expect(profileInput()).toBe(originalProfileInput);
    expect(nicknameInput()).toBe(originalNicknameInput);
    expect(screen.getByTestId('learner-profile-dialog-content')).toBe(
      dialogContent,
    );
    expect(profileInput()).toHaveValue('Draft kept through retention');
    expect(nicknameInput()).toHaveValue('Taylor');
    expect(mockTrackEvent).toHaveBeenCalledWith(
      PROFILE_ONBOARDING_EVENTS.RETENTION_CONTINUED,
      {
        source: 'guided',
        presentation: 'blocking',
        phase: 'save',
      },
    );
    expect(
      mockTrackEvent.mock.calls.filter(
        ([event]) => event === PROFILE_ONBOARDING_EVENTS.RETENTION_CONTINUED,
      ),
    ).toHaveLength(1);
    const retentionContinuedPayload = mockTrackEvent.mock.calls.find(
      ([event]) => event === PROFILE_ONBOARDING_EVENTS.RETENTION_CONTINUED,
    )?.[1];
    expectSafeRetentionAnalyticsPayload(retentionContinuedPayload);

    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.skip' }),
    );
    expect(
      mockTrackEvent.mock.calls.filter(
        ([event]) => event === PROFILE_ONBOARDING_EVENTS.RETENTION_SHOWN,
      ),
    ).toHaveLength(2);
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'module.profileOnboarding.dialog.retention.defer',
      }),
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

  test('keeps retention available when analytics throws or rejects', async () => {
    renderDialog({
      exitPolicy: 'blocking',
      presentation: 'blocking',
      onDefer: jest.fn().mockResolvedValue(true),
    });
    await screen.findByDisplayValue(existingProfile.learner_profile);
    mockTrackEvent
      .mockImplementationOnce(() => {
        throw new Error('analytics unavailable');
      })
      .mockRejectedValueOnce(new Error('analytics rejected'));

    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.skip' }),
    );
    expect(
      await screen.findByText(
        'module.profileOnboarding.dialog.retention.title',
      ),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.retention.continueSetup',
      }),
    );
    expect(profileInput()).toHaveValue(existingProfile.learner_profile);
  });

  test.each([
    [
      'throws synchronously',
      () => {
        throw new Error('analytics unavailable');
      },
    ],
    [
      'rejects asynchronously',
      () => Promise.reject(new Error('analytics rejected')),
    ],
  ])(
    'completes a successful final defer when skipped analytics %s',
    async (_analyticsFailure, failTracking) => {
      const onClose = jest.fn();
      const onDefer = jest.fn().mockResolvedValue(true);
      window.sessionStorage.setItem(
        'profile-onboarding-paste-draft:profile-v2:user-a',
        'Clear after final defer',
      );
      renderDialog({
        exitPolicy: 'blocking',
        presentation: 'blocking',
        onClose,
        onDefer,
      });
      await screen.findByDisplayValue(existingProfile.learner_profile);

      fireEvent.click(
        screen.getByRole('button', { name: 'module.profileOnboarding.skip' }),
      );
      await screen.findByText(
        'module.profileOnboarding.dialog.retention.title',
      );
      mockTrackEvent.mockImplementationOnce(failTracking);

      fireEvent.click(
        screen.getByRole('button', {
          name: 'module.profileOnboarding.dialog.retention.defer',
        }),
      );

      await waitFor(() => expect(onDefer).toHaveBeenCalledTimes(1));
      await waitFor(() => expect(onClose).toHaveBeenCalledWith('dismiss'));
      expect(onClose).toHaveBeenCalledTimes(1);
      expect(
        mockTrackEvent.mock.calls.filter(
          ([event]) => event === PROFILE_ONBOARDING_EVENTS.SKIPPED,
        ),
      ).toHaveLength(1);
      expect(
        window.sessionStorage.getItem(
          'profile-onboarding-paste-draft:profile-v2:user-a',
        ),
      ).toBeNull();
    },
  );

  test('keeps retention retryable, hides stale errors in a new cycle, and preserves research', async () => {
    const onClose = jest.fn();
    const deferRequest = deferred<boolean>();
    const onDefer = jest
      .fn()
      .mockReturnValueOnce(deferRequest.promise)
      .mockResolvedValue(false);
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingStatus.mockResolvedValue(onboardingStatus());
    const { props, rerender } = renderDialog({
      exitPolicy: 'blocking',
      presentation: 'blocking',
      onClose,
      onDefer,
    });
    await waitForCollectionSession();
    const conversation = mockConversationControls.at(-1)!;
    act(() => conversation.changeAssistantDraft('Unsubmitted answer'));

    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.skip' }),
    );
    await screen.findByText('module.profileOnboarding.dialog.retention.title');
    expect(onDefer).not.toHaveBeenCalled();
    expect(mockCreateProfileOnboardingSession).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledWith(
      PROFILE_ONBOARDING_EVENTS.RETENTION_SHOWN,
      {
        source: 'guided',
        presentation: 'blocking',
        phase: 'collect',
      },
    );
    expect(
      screen.getByRole('button', {
        name: FINISH_COLLECTION_LABEL,
        hidden: true,
      }),
    ).toBeDisabled();

    const finalSkipButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.retention.defer',
    });
    const continueButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.retention.continueSetup',
    });
    fireEvent.click(finalSkipButton);
    await waitFor(() => expect(onDefer).toHaveBeenCalledWith(SESSION_ID));
    expect(finalSkipButton).toBeDisabled();
    expect(continueButton).toBeDisabled();
    fireEvent.click(finalSkipButton);
    fireEvent.click(continueButton);
    expect(onDefer).toHaveBeenCalledTimes(1);

    await act(async () => deferRequest.resolve(false));
    expect(onClose).not.toHaveBeenCalled();
    expect(
      screen.getByText('module.profileOnboarding.dialog.retention.title'),
    ).toBeInTheDocument();
    rerender(
      <LearnerProfileDialog
        {...props}
        externalErrorMessage='Skip unavailable'
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Skip unavailable');
    await waitFor(() => expect(finalSkipButton).toBeEnabled());
    fireEvent.click(finalSkipButton);
    await waitFor(() => expect(onDefer).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(continueButton).toBeEnabled());
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      PROFILE_ONBOARDING_EVENTS.SKIPPED,
      expect.anything(),
    );

    fireEvent.click(continueButton);
    await waitFor(() =>
      expect(
        screen.getByLabelText('module.profileOnboarding.title'),
      ).toHaveFocus(),
    );
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByText('Skip unavailable')).not.toBeInTheDocument();
    expect(mockCreateProfileOnboardingSession).toHaveBeenCalledTimes(1);
    expect(mockConversationControls.at(-1)).toBe(conversation);
    expect(conversation.assistantDraft()).toBe('Unsubmitted answer');

    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.skip' }),
    );
    await screen.findByText('module.profileOnboarding.dialog.retention.title');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByText('Skip unavailable')).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.retention.continueSetup',
      }),
    );
    await waitFor(() =>
      expect(
        screen.getByLabelText('module.profileOnboarding.title'),
      ).toHaveFocus(),
    );

    fireEvent.click(screen.getByRole('button', { name: 'finish collection' }));
    await continueCollectionToSave();
    expect(
      await screen.findByDisplayValue('Collection draft'),
    ).toBeInTheDocument();
    expect(mockOptimizeLearnerProfile).not.toHaveBeenCalled();
  });

  test('succeeds on retry after a final defer failure', async () => {
    const onClose = jest.fn();
    const onDefer = jest
      .fn()
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true);
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingStatus.mockResolvedValue(onboardingStatus());
    const { props, rerender } = renderDialog({
      exitPolicy: 'blocking',
      presentation: 'blocking',
      onClose,
      onDefer,
    });
    await waitForCollectionSession();
    act(() =>
      mockConversationControls
        .at(-1)
        ?.changeAssistantDraft('Clear after retry succeeds'),
    );

    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.skip' }),
    );
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'module.profileOnboarding.dialog.retention.defer',
      }),
    );
    await waitFor(() => expect(onDefer).toHaveBeenCalledTimes(1));
    expect(onClose).not.toHaveBeenCalled();
    expect(
      window.sessionStorage.getItem(
        'profile-onboarding-paste-draft:profile-v2:user-a',
      ),
    ).toBe('Clear after retry succeeds');

    rerender(
      <LearnerProfileDialog
        {...props}
        externalErrorMessage='Skip unavailable'
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Skip unavailable');
    const retryButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.dialog.retention.defer',
    });
    await waitFor(() => expect(retryButton).toBeEnabled());
    fireEvent.click(retryButton);

    await waitFor(() => expect(onDefer).toHaveBeenCalledTimes(2));
    expect(onClose).toHaveBeenCalledWith('dismiss');
    expect(
      mockTrackEvent.mock.calls.filter(
        ([event]) => event === PROFILE_ONBOARDING_EVENTS.SKIPPED,
      ),
    ).toHaveLength(1);
    expect(
      window.sessionStorage.getItem(
        'profile-onboarding-paste-draft:profile-v2:user-a',
      ),
    ).toBeNull();
  });

  test('does not open retention during an active collection run', async () => {
    const onClose = jest.fn();
    const onDefer = jest.fn().mockResolvedValue(true);
    mockGetLearnerProfile.mockResolvedValue(emptyProfile);
    mockGetProfileOnboardingStatus.mockResolvedValue(onboardingStatus());
    renderDialog({
      exitPolicy: 'blocking',
      presentation: 'blocking',
      onClose,
      onDefer,
    });
    await waitForCollectionSession();

    const skipButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.skip',
    });
    const conversation = mockConversationControls.at(-1)!;
    act(() => conversation.changeAssistantDraft('Clear only after success'));
    act(() => conversation.setRunInFlight(true));

    expect(skipButton).toBeDisabled();
    fireEvent.click(skipButton);
    expect(onDefer).not.toHaveBeenCalled();

    act(() => conversation.setRunInFlight(false));
    expect(skipButton).toBeEnabled();
    fireEvent.click(skipButton);

    await screen.findByText('module.profileOnboarding.dialog.retention.title');
    expect(onDefer).not.toHaveBeenCalled();
    expect(
      window.sessionStorage.getItem(
        'profile-onboarding-paste-draft:profile-v2:user-a',
      ),
    ).toBe('Clear only after success');
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.retention.defer',
      }),
    );

    await waitFor(() => expect(onDefer).toHaveBeenCalledWith(SESSION_ID));
    expect(onClose).toHaveBeenCalledWith('dismiss');
    expect(
      window.sessionStorage.getItem(
        'profile-onboarding-paste-draft:profile-v2:user-a',
      ),
    ).toBeNull();
  });

  test('confirms before discarding dirty settings edits', async () => {
    const onClose = jest.fn();
    window.sessionStorage.setItem(
      'profile-onboarding-paste-draft:profile-v2:user-a',
      'Draft to discard',
    );
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
    await waitFor(() =>
      expect(
        screen.getByText('module.profileOnboarding.dialog.discardTitle'),
      ).toHaveFocus(),
    );
    expect(screen.getByTestId('learner-profile-dialog-body')).toHaveClass(
      'overflow-y-auto',
    );
    expect(screen.getByTestId('learner-profile-dialog-body')).toContainElement(
      informationUsageControl('inline'),
    );
    expect(
      screen.getByTestId('learner-profile-dialog-footer'),
    ).toContainElement(informationUsageControl('popover'));
    expect(informationUsageControl('popover').parentElement).toHaveClass(
      '[@media(max-height:620px)]:hidden',
    );
    expect(informationUsageControl('inline')).toHaveClass(
      '[@media(max-height:620px)]:block',
    );
    expect(
      screen.getByTestId('learner-profile-confirmation-discard'),
    ).toHaveClass('[@media(max-height:620px)]:justify-start');
    const confirmationActions = screen.getByTestId(
      'learner-profile-dialog-confirmation-actions',
    );
    expect(confirmationActions).toContainElement(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.keepEditing',
      }),
    );
    expect(confirmationActions).toContainElement(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.discard',
      }),
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.dialog.discard',
      }),
    );
    await waitFor(() => expect(onClose).toHaveBeenCalledWith('dismiss'));
    expect(
      window.sessionStorage.getItem(
        'profile-onboarding-paste-draft:profile-v2:user-a',
      ),
    ).toBeNull();
  });

  test('preserves an open draft when the tracking callback identity changes', async () => {
    const { rerender, props } = renderDialog();
    await screen.findByDisplayValue(existingProfile.learner_profile);
    fireEvent.change(profileInput(), { target: { value: 'Unsaved edit' } });

    mockTrackEventIdentity = jest.fn();
    rerender(<LearnerProfileDialog {...props} />);

    expect(profileInput()).toHaveValue('Unsaved edit');
    expect(mockGetLearnerProfile).toHaveBeenCalledTimes(1);
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
    mockGetProfileOnboardingStatus
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
    mockGetProfileOnboardingStatus.mockResolvedValue(
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
