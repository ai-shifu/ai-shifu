import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import ShifuSettingDialog from './ShifuSetting';
import { SSE } from 'sse.js';

const mockTtsConfig = jest.fn();
const mockListMinimaxTtsVoices = jest.fn();
const mockGetMinimaxTtsCloneCost = jest.fn();
const mockAskConfig = jest.fn();
const mockAskPreview = jest.fn();
const mockCreditToast = jest.fn();
const mockUserState = { userInfo: { user_id: 'owner-1' } };
const mockGetShifuDetail = jest.fn();
const mockSaveShifuDetail = jest.fn();
const mockTrackEvent = jest.fn();
const mockToast = jest.fn();
const mockGetFollowUpModelCatalog = jest.fn();
const mockGetCourseModelOptions = jest.fn();
const mockAskSettingsSection = jest.fn();
const mockMainModelSelector = jest.fn();
const mockMiniMaxCloneDialog = jest.fn();
const mockFormMethods = jest.fn();
const mockBillingOverview = { debug_allowed: undefined as boolean | undefined };
const mockCurrentShifu = {
  bid: 'course-1',
  readonly: false,
  created_user_bid: 'owner-1',
};

const mockEnvState = {
  currencySymbol: '¥',
  minimumPaidCoursePrice: 0.5,
  billingEnabled: 'false',
};

jest.mock('sse.js', () => ({
  SSE: jest.fn(() => ({
    addEventListener: jest.fn(),
    stream: jest.fn(),
    close: jest.fn(),
  })),
}));
jest.mock('@/lib/request', () => ({
  ...jest.requireActual('@/lib/request'),
  attachSseBusinessResponseFallback: jest.fn(),
}));
jest.mock('@/lib/creditInsufficientToast', () => ({
  ...jest.requireActual('@/lib/creditInsufficientToast'),
  showCreditInsufficientToast: (...args: unknown[]) => mockCreditToast(...args),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    ttsConfig: (...args: unknown[]) => mockTtsConfig(...args),
    listMinimaxTtsVoices: (...args: unknown[]) =>
      mockListMinimaxTtsVoices(...args),
    getMinimaxTtsCloneCost: (...args: unknown[]) =>
      mockGetMinimaxTtsCloneCost(...args),
    askConfig: (...args: unknown[]) => mockAskConfig(...args),
    askPreview: (...args: unknown[]) => mockAskPreview(...args),
    getCourseModelOptions: (...args: unknown[]) =>
      mockGetCourseModelOptions(...args),
    getShifuDetail: (...args: unknown[]) => mockGetShifuDetail(...args),
    saveShifuDetail: (...args: unknown[]) => mockSaveShifuDetail(...args),
  },
}));

jest.mock('@/store', () => ({
  useShifu: () => ({
    currentShifu: mockCurrentShifu,
    models: [],
  }),
  useUserStore: Object.assign(
    (selector: (state: typeof mockUserState) => unknown) =>
      selector(mockUserState),
    {
      getState: () => ({ getToken: () => '' }),
    },
  ),
  useEnvStore: (selector: (state: typeof mockEnvState) => unknown) =>
    selector(mockEnvState),
}));

jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('@/hooks/useBillingData', () => ({
  useBillingOverview: () => ({ data: mockBillingOverview }),
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('@/hooks/useExclusiveAudio', () => ({
  __esModule: true,
  default: () => ({
    requestExclusive: jest.fn(),
    releaseExclusive: jest.fn(),
  }),
}));

jest.mock('@/lib/liveVoiceFollowUp', () => ({
  getFollowUpModelCatalog: (...args: unknown[]) =>
    mockGetFollowUpModelCatalog(...args),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { resolvedLanguage: 'en-US', language: 'en-US' },
  }),
}));

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({
    children,
    href,
  }: {
    children: React.ReactNode;
    href: string;
  }) => <a href={href}>{children}</a>,
}));

jest.mock('@/components/model-list', () => () => null);
jest.mock('@/components/ui/Form', () => {
  const actual = jest.requireActual('@/components/ui/Form');
  return {
    ...actual,
    Form: (props: Record<string, unknown>) => {
      mockFormMethods(props);
      const ActualForm = actual.Form;
      return <ActualForm {...props} />;
    },
  };
});
jest.mock('@/components/model-list/CourseModelSelect', () => ({
  __esModule: true,
  default: (props: Record<string, unknown>) => {
    mockMainModelSelector(props);
    return null;
  },
}));
jest.mock('@/components/shifu-setting/AskSettingsSection', () => ({
  __esModule: true,
  default: (props: Record<string, unknown>) => {
    mockAskSettingsSection(props);
    return null;
  },
}));
jest.mock(
  '@/components/shifu-setting/MiniMaxVoiceCloneDialog',
  () => (props: Record<string, unknown>) => {
    mockMiniMaxCloneDialog(props);
    return null;
  },
);

jest.mock('@/components/ui/Sheet', () => ({
  Sheet: ({
    children,
    open,
    onOpenChange,
  }: {
    children: React.ReactNode;
    open: boolean;
    onOpenChange: (open: boolean) => void;
  }) => (
    <div>
      {children}
      {open ? (
        <button
          type='button'
          aria-label='close-settings'
          onClick={() => onOpenChange(false)}
        />
      ) : null}
    </div>
  ),
  SheetTrigger: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  SheetContent: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  SheetHeader: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  SheetTitle: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

const createDeferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });
  return { promise, resolve, reject };
};

const renderOpenSettings = (onSave = jest.fn()) => {
  render(
    <ShifuSettingDialog
      shifuId='course-1'
      openSignal='analytics-test'
      onSave={onSave}
    />,
  );
  return { onSave };
};

describe('ShifuSettingDialog analytics producer', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockTtsConfig.mockResolvedValue({ providers: [], model_options: [] });
    mockListMinimaxTtsVoices.mockResolvedValue({ voices: [] });
    mockGetMinimaxTtsCloneCost.mockResolvedValue({});
    mockCurrentShifu.readonly = false;
    mockAskConfig.mockResolvedValue({ providers: [] });
    mockSaveShifuDetail.mockResolvedValue(undefined);
    mockTrackEvent.mockImplementation(() => undefined);
    mockGetFollowUpModelCatalog.mockResolvedValue([]);
    mockEnvState.billingEnabled = 'false';
    mockUserState.userInfo.user_id = 'owner-1';
    mockAskPreview.mockResolvedValue({ answer: 'Preview answer' });
    mockBillingOverview.debug_allowed = undefined;
    mockGetShifuDetail.mockResolvedValue({
      bid: 'course-1',
      name: 'Private course name',
      description: 'Private course description',
      keywords: ['private keyword'],
      model: '',
      price: 1,
      avatar: '',
      temperature: 0,
      system_prompt: 'Private system prompt',
      ask_model: '',
      ask_temperature: 0,
      ask_provider_config: {
        provider: 'llm',
        mode: 'provider_only',
        config: { api_key: 'private-provider-secret' },
      },
      tts_enabled: false,
      default_listen_mode_enabled: true,
      use_learner_language: true,
    });
  });

  it.each([false, true])(
    'emits the exact allowlist only after the settings API succeeds (catalog pending=%s)',
    async pendingCatalog => {
      if (pendingCatalog) {
        mockGetFollowUpModelCatalog.mockReturnValue(new Promise(() => {}));
      }
      const save = createDeferred<void>();
      mockSaveShifuDetail.mockReturnValue(save.promise);
      const { onSave } = renderOpenSettings();

      await screen.findByDisplayValue('Private course name');
      fireEvent.click(screen.getByLabelText('close-settings'));

      await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
      expect(mockTrackEvent).not.toHaveBeenCalled();
      expect(onSave).not.toHaveBeenCalled();

      await act(async () => {
        save.resolve();
        await save.promise;
      });

      await waitFor(() => {
        expect(mockTrackEvent).toHaveBeenCalledWith(
          'creator_shifu_setting_save',
          {
            shifu_bid: 'course-1',
            save_type: 'manual',
            tts_enabled: false,
            default_listen_mode_enabled: false,
            use_learner_language: true,
            follow_up_mode: 'text',
            price_tier: 'standard_paid',
            main_model_index: '1',
            main_model_fallback: false,
            follow_up_model_fallback: false,
            follow_up_model_index: '1',
          },
        );
      });
      expect(mockTrackEvent).toHaveBeenCalledTimes(1);
      expect(mockTrackEvent.mock.calls[0][1]).not.toHaveProperty('name');
      expect(mockTrackEvent.mock.calls[0][1]).not.toHaveProperty('description');
      expect(mockTrackEvent.mock.calls[0][1]).not.toHaveProperty(
        'system_prompt',
      );
      expect(mockTrackEvent.mock.calls[0][1]).not.toHaveProperty(
        'ask_provider_config',
      );
      expect(onSave).toHaveBeenCalledTimes(1);
    },
  );

  it.each([false, true])(
    'emits nothing when the settings API fails (catalog pending=%s)',
    async pendingCatalog => {
      if (pendingCatalog) {
        mockGetFollowUpModelCatalog.mockReturnValue(new Promise(() => {}));
      }
      mockSaveShifuDetail.mockRejectedValue(new Error('Private API failure'));
      const { onSave } = renderOpenSettings();

      await screen.findByDisplayValue('Private course name');
      fireEvent.click(screen.getByLabelText('close-settings'));

      await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
      await act(async () => {
        await Promise.resolve();
      });

      expect(mockTrackEvent).not.toHaveBeenCalled();
      expect(onSave).not.toHaveBeenCalled();
      expect(screen.getByLabelText('close-settings')).toBeInTheDocument();
    },
  );

  it.each([false, true])(
    'completes the successful save flow when analytics throws (catalog pending=%s)',
    async pendingCatalog => {
      if (pendingCatalog) {
        mockGetFollowUpModelCatalog.mockReturnValue(new Promise(() => {}));
      }
      mockTrackEvent.mockImplementation(() => {
        throw new Error('analytics unavailable');
      });
      const { onSave } = renderOpenSettings();

      await screen.findByDisplayValue('Private course name');
      fireEvent.click(screen.getByLabelText('close-settings'));

      await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
      await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
      expect(screen.queryByLabelText('close-settings')).not.toBeInTheDocument();
    },
  );

  it.each(['owner-1', 'collaborator-1'])(
    'sends course ownership context for ask previews by %s',
    async userId => {
      mockUserState.userInfo.user_id = userId;
      mockEnvState.billingEnabled = 'true';
      mockBillingOverview.debug_allowed = userId === 'owner-1';
      renderOpenSettings();
      await screen.findByDisplayValue('Private course name');
      const latestProps = () =>
        mockAskSettingsSection.mock.calls.at(-1)?.[0] as {
          textDebugAllowed: boolean;
          setAskPreviewQuery: (query: string) => void;
          handleAskPreview: () => Promise<void>;
        };
      expect(latestProps().textDebugAllowed).toBe(true);
      act(() => latestProps().setAskPreviewQuery('Preview question'));
      await act(async () => latestProps().handleAskPreview());
      expect(mockAskPreview).toHaveBeenCalledWith(
        expect.objectContaining({
          shifu_bid: 'course-1',
          query: 'Preview question',
        }),
        {
          skipErrorToast: true,
          creditInsufficientAudience:
            userId === 'owner-1' ? 'teacher' : 'teacher-collaborator',
        },
      );
      expect(mockAskPreview.mock.calls[0][0]).not.toHaveProperty('creator_bid');
    },
  );

  it('directs collaborators to the owner when preview credits are unavailable', async () => {
    mockUserState.userInfo.user_id = 'collaborator-1';
    mockEnvState.billingEnabled = 'true';
    mockBillingOverview.debug_allowed = false;
    mockAskPreview.mockRejectedValue(
      Object.assign(new Error('owner credits unavailable'), { code: 7101 }),
    );
    renderOpenSettings();
    await screen.findByDisplayValue('Private course name');
    const latestProps = () => mockAskSettingsSection.mock.calls.at(-1)?.[0];
    act(() => latestProps().setAskPreviewQuery('Preview question'));
    await act(async () => latestProps().handleAskPreview());
    expect(mockCreditToast).toHaveBeenCalledWith({
      audience: 'teacher-collaborator',
      code: 7101,
    });
  });

  it('sends course ownership context for TTS even when the collaborator has no debug credits', async () => {
    mockUserState.userInfo.user_id = 'collaborator-1';
    mockEnvState.billingEnabled = 'true';
    mockBillingOverview.debug_allowed = false;
    mockTtsConfig.mockResolvedValue({
      providers: [
        {
          name: 'fake',
          label: 'Fake',
          speed: { min: 0.5, max: 2, step: 0.1, default: 1 },
          voices: [{ value: 'voice-1', label: 'Voice' }],
          models: [{ value: 'tts-model', label: 'TTS' }],
        },
      ],
      model_options: [],
    });
    const detail = await mockGetShifuDetail();
    mockGetShifuDetail.mockResolvedValue({
      ...detail,
      tts_enabled: true,
      tts_provider: 'fake',
      tts_model: 'tts-model',
      tts_voice_id: 'voice-1',
      tts_speed: 1,
    });
    renderOpenSettings();
    await screen.findByDisplayValue('Private course name');
    const button = await screen.findByRole('button', {
      name: 'module.shifuSetting.ttsPreview',
    });
    expect(button).not.toBeDisabled();
    fireEvent.click(button);
    await waitFor(() => expect(SSE).toHaveBeenCalledTimes(1));
    expect(JSON.parse((SSE as jest.Mock).mock.calls[0][1].payload)).toEqual(
      expect.objectContaining({ shifu_bid: 'course-1' }),
    );
  });

  it('ignores MiniMax refreshes that finish after a newer request', async () => {
    mockTtsConfig.mockResolvedValue({
      providers: [
        {
          name: 'minimax',
          label: 'MiniMax',
          supports_voice_cloning: true,
          speed: { min: 0.5, max: 2, step: 0.1, default: 1 },
          voices: [{ value: 'voice-1', label: 'Voice' }],
          models: [{ value: 'tts-model', label: 'TTS' }],
        },
      ],
      model_options: [],
    });
    mockListMinimaxTtsVoices.mockResolvedValue({ voices: [] });
    const initialDetail = await mockGetShifuDetail();
    mockGetShifuDetail.mockResolvedValue({
      ...initialDetail,
      tts_enabled: true,
      tts_provider: 'minimax',
      tts_model: 'tts-model',
      tts_voice_id: 'voice-1',
      tts_speed: 1,
    });

    type CloneCostResponse = {
      estimated_credits?: string;
      can_submit?: boolean;
    };
    const costRequests: Array<
      ReturnType<typeof createDeferred<CloneCostResponse>>
    > = [];
    mockGetMinimaxTtsCloneCost.mockImplementation(() => {
      const request = createDeferred<CloneCostResponse>();
      costRequests.push(request);
      return request.promise;
    });

    renderOpenSettings();
    await waitFor(() => expect(costRequests.length).toBeGreaterThan(0));
    const olderRequests = [...costRequests];
    const dialogProps = mockMiniMaxCloneDialog.mock.calls.at(-1)?.[0] as {
      onRefreshCost: () => Promise<void>;
    };
    const startRefresh = async () => {
      const previousCount = costRequests.length;
      const completion = dialogProps.onRefreshCost();
      await waitFor(() => expect(costRequests).toHaveLength(previousCount + 1));
      return { completion, request: costRequests.at(-1)! };
    };
    const consoleErrorSpy = jest
      .spyOn(console, 'error')
      .mockImplementation(() => undefined);
    const newerRefresh = dialogProps.onRefreshCost();
    await waitFor(() =>
      expect(costRequests).toHaveLength(olderRequests.length + 1),
    );
    const newerRequest = costRequests.at(-1)!;

    await act(async () => {
      newerRequest.resolve({ estimated_credits: '10', can_submit: false });
      await newerRefresh;
    });
    expect(
      screen.getByText('module.shifuSetting.minimaxCloneCostCredits'),
    ).toBeInTheDocument();

    await act(async () => {
      olderRequests.forEach(request =>
        request.reject(new Error('stale clone cost request failed')),
      );
      await Promise.all(
        olderRequests.map(request => request.promise.catch(() => undefined)),
      );
    });

    expect(
      screen.getByText('module.shifuSetting.minimaxCloneCostCredits'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('module.shifuSetting.minimaxCloneCostUnavailable'),
    ).not.toBeInTheDocument();

    const olderSuccess = await startRefresh();
    const latestFailure = await startRefresh();
    await act(async () => {
      latestFailure.request.reject(
        new Error('latest clone cost request failed'),
      );
      await latestFailure.completion;
    });
    expect(
      screen.getByText('module.shifuSetting.minimaxCloneCostUnavailable'),
    ).toBeInTheDocument();

    await act(async () => {
      olderSuccess.request.resolve({
        estimated_credits: '99',
        can_submit: true,
      });
      await olderSuccess.completion;
    });
    expect(
      screen.getByText('module.shifuSetting.minimaxCloneCostUnavailable'),
    ).toBeInTheDocument();
    expect(consoleErrorSpy).toHaveBeenCalledTimes(olderRequests.length + 1);
    consoleErrorSpy.mockRestore();
  });

  it.each([
    {
      userId: 'collaborator-1',
      readonly: true,
      demoUrl: 'https://example.com/demo.mp3',
    },
    {
      userId: 'owner-1',
      readonly: false,
      demoUrl: 'https://example.com/demo.mp3',
    },
    { userId: 'collaborator-1', readonly: true, demoUrl: '   ' },
  ])(
    'handles cached voice demos for $userId (readonly=$readonly, demo=$demoUrl)',
    async ({ userId, readonly, demoUrl }) => {
      mockUserState.userInfo.user_id = userId;
      mockCurrentShifu.readonly = readonly;
      mockEnvState.billingEnabled = 'true';
      mockBillingOverview.debug_allowed = false;
      mockTtsConfig.mockResolvedValue({
        providers: [
          {
            name: 'minimax',
            label: 'MiniMax',
            supports_voice_cloning: true,
            speed: { min: 0.5, max: 2, step: 0.1, default: 1 },
            voices: [{ value: 'voice-1', label: 'Voice' }],
            models: [{ value: 'tts-model', label: 'TTS' }],
          },
        ],
        model_options: [],
      });
      mockListMinimaxTtsVoices.mockResolvedValue({
        voices: [
          {
            voice_bid: 'clone-1',
            voice_id: 'cloned-voice',
            display_name: 'Saved voice',
            status: 'ready',
            minimax_demo_audio_url: demoUrl,
          },
        ],
      });
      const detail = await mockGetShifuDetail();
      mockGetShifuDetail.mockResolvedValue({
        ...detail,
        tts_enabled: true,
        tts_provider: 'minimax',
        tts_model: 'tts-model',
        tts_voice_id: 'voice-1',
        tts_speed: 1,
      });
      const audio = document.createElement('audio');
      const play = jest.spyOn(audio, 'play').mockResolvedValue();
      const pause = jest.spyOn(audio, 'pause').mockImplementation(() => {});
      jest.spyOn(audio, 'load').mockImplementation(() => {});
      const createAudio = jest.spyOn(window, 'Audio').mockReturnValue(audio);

      try {
        renderOpenSettings();
        expect(
          await screen.findByText(
            'module.shifuSetting.minimaxCloneCostUnavailable',
          ),
        ).toBeInTheDocument();
        const button = await screen.findByTitle(
          demoUrl.trim()
            ? 'module.shifuSetting.minimaxClonePreview'
            : 'module.shifuSetting.minimaxClonePreviewUnavailable',
        );
        if (demoUrl.trim()) {
          expect(button).toBeEnabled();
          fireEvent.click(button);
          await waitFor(() => expect(play).toHaveBeenCalledTimes(1));
          expect(createAudio).toHaveBeenCalledWith(demoUrl);
          fireEvent.click(button);
          expect(pause).toHaveBeenCalledTimes(1);
        } else {
          expect(button).toBeDisabled();
          fireEvent.click(button);
          expect(createAudio).not.toHaveBeenCalled();
        }
        expect(SSE).not.toHaveBeenCalled();
        expect(mockCreditToast).not.toHaveBeenCalled();
      } finally {
        createAudio.mockRestore();
      }
    },
  );

  it('keeps text debug gated while exposing Live and the saved default model', async () => {
    mockEnvState.billingEnabled = 'true';
    mockGetFollowUpModelCatalog.mockResolvedValue([
      {
        model: '1',
        display_name: 'Text model',
        interaction_mode: 'text',
        allowed_roles: ['main', 'follow_up'],
        billing_mode: 'billable',
        voices: [],
        is_default: true,
      },
      {
        model: 'gemini-3.8-live',
        display_name: 'Gemini Live',
        interaction_mode: 'live_voice',
        allowed_roles: ['follow_up'],
        billing_mode: 'free_preview',
        voices: [{ voice_id: 'Kore', style: 'Firm' }],
      },
    ]);
    renderOpenSettings();

    await waitFor(() => {
      const latestProps = mockAskSettingsSection.mock.calls.at(-1)?.[0] as {
        readonly: boolean;
        textDebugAllowed: boolean;
        askModelOptions: Array<{ value: string; disabled?: boolean }>;
      };
      expect(latestProps).toEqual(
        expect.objectContaining({
          readonly: false,
          textDebugAllowed: false,
        }),
      );
      expect(latestProps.askModelOptions).toEqual([
        expect.objectContaining({ value: '1', disabled: false }),
        expect.objectContaining({
          value: 'gemini-3.8-live',
          disabled: false,
        }),
      ]);
    });
  });

  it.each(
    [false, undefined].flatMap(debugAllowed => [
      { debugAllowed, savedModel: '1', markedDefault: false },
      { debugAllowed, savedModel: '', markedDefault: true },
      { debugAllowed, savedModel: '', markedDefault: false },
    ]),
  )(
    'allows reverting to saved "$savedModel" (default=$markedDefault, debug=$debugAllowed)',
    async ({ debugAllowed, savedModel, markedDefault }) => {
      mockEnvState.billingEnabled = 'true';
      mockBillingOverview.debug_allowed = debugAllowed;
      const textModels = [
        {
          model: '1',
          display_name: 'Saved',
          interaction_mode: 'text',
          voices: [],
          is_default: markedDefault,
        },
        {
          model: '3',
          display_name: 'Other',
          interaction_mode: 'text',
          voices: [],
        },
      ];
      // A marked default takes precedence over the first catalog entry;
      // without a marker, ModelList uses that first entry for its Default alias.
      if (markedDefault) {
        textModels.reverse();
      }
      mockGetFollowUpModelCatalog.mockResolvedValue([
        ...textModels,
        {
          model: 'live-model',
          display_name: 'Live',
          interaction_mode: 'live_voice',
          voices: [{ voice_id: 'Kore', style: 'Firm' }],
        },
      ]);
      mockGetShifuDetail.mockResolvedValue({
        bid: 'course-1',
        name: 'Private course name',
        description: '',
        keywords: [],
        model: '',
        price: 1,
        avatar: '',
        temperature: 0,
        system_prompt: '',
        ask_model: savedModel,
        ask_temperature: 0,
        ask_provider_config: {
          provider: 'llm',
          mode: 'provider_only',
          config: {},
        },
        tts_enabled: false,
        default_listen_mode_enabled: false,
        use_learner_language: false,
      });
      renderOpenSettings();
      const latestProps = () =>
        mockAskSettingsSection.mock.calls.at(-1)?.[0] as {
          askModel: string;
          askModelOptions: Array<{ value: string; disabled?: boolean }>;
          onAskModelChange: (model: string) => void;
          isLiveVoiceFollowUp: boolean;
          textDebugAllowed: boolean;
        };
      await waitFor(() => expect(latestProps().askModel).toBe(savedModel));
      const expectedOptions = [
        ...textModels.map(item =>
          expect.objectContaining({
            value: item.model,
            disabled: item.model !== '1',
          }),
        ),
        expect.objectContaining({ value: 'live-model', disabled: false }),
      ];
      expect(latestProps().askModelOptions).toEqual(expectedOptions);
      act(() => latestProps().onAskModelChange('live-model'));
      expect(latestProps().isLiveVoiceFollowUp).toBe(true);
      expect(latestProps().askModelOptions).toEqual(expectedOptions);
      expect(latestProps().textDebugAllowed).toBe(false);
      act(() => latestProps().onAskModelChange(savedModel));
      expect(latestProps().isLiveVoiceFollowUp).toBe(false);
      fireEvent.click(screen.getByLabelText('close-settings'));
      await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
      expect(mockSaveShifuDetail.mock.calls[0][0]).toEqual(
        expect.objectContaining({
          ask_model: '1',
          ask_provider_config: {
            provider: 'llm',
            mode: 'provider_only',
            config: {},
          },
        }),
      );
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'creator_shifu_setting_save',
        {
          shifu_bid: 'course-1',
          save_type: 'manual',
          tts_enabled: false,
          default_listen_mode_enabled: false,
          use_learner_language: false,
          follow_up_mode: 'text',
          price_tier: 'standard_paid',
          main_model_index: '1',
          main_model_fallback: false,
          follow_up_model_fallback: false,
          follow_up_model_index: '1',
        },
      );
      expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    },
  );

  it.each([false, true])(
    'saves and closes before the catalog resolves (edited=%s)',
    async edited => {
      const catalog = createDeferred<unknown[]>();
      mockGetFollowUpModelCatalog.mockReturnValue(catalog.promise);
      const { onSave } = renderOpenSettings();
      const name = await screen.findByDisplayValue('Private course name');
      if (edited) {
        fireEvent.change(name, { target: { value: 'Updated course name' } });
      }

      fireEvent.click(screen.getByLabelText('close-settings'));

      await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
      expect(screen.queryByLabelText('close-settings')).not.toBeInTheDocument();
      expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1);
      expect(mockSaveShifuDetail.mock.calls[0][0]).toEqual(
        expect.objectContaining({
          name: edited ? 'Updated course name' : 'Private course name',
          ask_provider_config: {
            provider: 'llm',
            mode: 'provider_only',
            config: { api_key: 'private-provider-secret' },
          },
        }),
      );
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'creator_shifu_setting_save',
        {
          shifu_bid: 'course-1',
          save_type: 'manual',
          tts_enabled: false,
          default_listen_mode_enabled: false,
          use_learner_language: true,
          follow_up_mode: 'text',
          price_tier: 'standard_paid',
          main_model_index: '1',
          main_model_fallback: false,
          follow_up_model_fallback: false,
          follow_up_model_index: '1',
        },
      );

      await act(async () => {
        catalog.resolve([
          { model: 'late-live-model', interaction_mode: 'live_voice' },
        ]);
        await catalog.promise;
      });
      expect(screen.queryByLabelText('close-settings')).not.toBeInTheDocument();
      expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1);
      expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    },
  );

  it.each(['unavailable', 'failed', 'loading'] as const)(
    'preserves an existing Live config when the catalog is %s',
    async catalogState => {
      if (catalogState === 'failed') {
        mockGetFollowUpModelCatalog.mockRejectedValue(
          new Error('catalog unavailable'),
        );
      } else if (catalogState === 'loading') {
        mockGetFollowUpModelCatalog.mockReturnValue(new Promise(() => {}));
      } else {
        mockGetFollowUpModelCatalog.mockResolvedValue([]);
      }
      mockGetShifuDetail.mockResolvedValue({
        bid: 'course-1',
        name: 'Private course name',
        description: 'Private course description',
        keywords: [],
        model: '',
        price: 1,
        avatar: '',
        temperature: 0,
        system_prompt: '',
        ask_model: 'opaque-existing-model-id',
        ask_temperature: 0,
        ask_provider_config: {
          provider: 'llm',
          mode: 'provider_only',
          config: { live_voice: 'Puck' },
        },
        tts_enabled: false,
        default_listen_mode_enabled: false,
        use_learner_language: false,
      });
      renderOpenSettings();
      await screen.findByDisplayValue('Private course name');
      await waitFor(() => {
        expect(mockAskSettingsSection.mock.calls.at(-1)?.[0]).toEqual(
          expect.objectContaining({
            isLiveVoiceFollowUp: true,
            liveVoice: 'Puck',
          }),
        );
      });

      fireEvent.click(screen.getByLabelText('close-settings'));

      await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
      expect(mockSaveShifuDetail.mock.calls[0][0]).toEqual(
        expect.objectContaining({
          ask_provider_config: {
            provider: 'llm',
            mode: 'provider_only',
            config: { live_voice: 'Puck' },
          },
        }),
      );
      await waitFor(() => {
        expect(mockTrackEvent).toHaveBeenCalledWith(
          'creator_shifu_setting_save',
          expect.objectContaining({ follow_up_mode: 'live_voice' }),
        );
      });
      expect(screen.queryByLabelText('close-settings')).not.toBeInTheDocument();
      expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    },
  );

  it('lets explicit text mode override a stale persisted Live voice field', async () => {
    mockGetFollowUpModelCatalog.mockResolvedValue([]);
    mockGetShifuDetail.mockResolvedValue({
      bid: 'course-1',
      name: 'Private course name',
      description: 'Private course description',
      keywords: [],
      model: '',
      price: 1,
      avatar: '',
      temperature: 0,
      system_prompt: '',
      ask_model: 'opaque-existing-model-id',
      ask_temperature: 0,
      follow_up_mode: 'text',
      ask_provider_config: {
        provider: 'llm',
        mode: 'provider_only',
        config: { live_voice: 'Puck' },
      },
      tts_enabled: false,
      default_listen_mode_enabled: false,
      use_learner_language: false,
    });
    renderOpenSettings();

    await waitFor(() => {
      expect(mockAskSettingsSection.mock.calls.at(-1)?.[0]).toEqual(
        expect.objectContaining({ isLiveVoiceFollowUp: false }),
      );
    });
    fireEvent.click(screen.getByLabelText('close-settings'));
    await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
    await waitFor(() => {
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'creator_shifu_setting_save',
        expect.objectContaining({ follow_up_mode: 'text' }),
      );
    });
  });

  it('forces Live to built-in provider-only configuration with the default voice', async () => {
    mockGetFollowUpModelCatalog.mockResolvedValue([
      {
        model: '1',
        display_name: 'Text model',
        interaction_mode: 'text',
        allowed_roles: ['main', 'follow_up'],
        billing_mode: 'billable',
        voices: [],
        is_default: true,
      },
      {
        model: 'gemini-3.8-live',
        display_name: 'Gemini Live',
        interaction_mode: 'live_voice',
        allowed_roles: ['follow_up'],
        billing_mode: 'free_preview',
        voices: [{ voice_id: 'Kore', style: 'Firm' }],
      },
    ]);
    mockGetShifuDetail.mockResolvedValue({
      bid: 'course-1',
      name: 'Private course name',
      description: 'Private course description',
      keywords: [],
      model: '',
      price: 1,
      avatar: '',
      temperature: 0,
      system_prompt: '',
      ask_model: '1',
      ask_temperature: 0,
      ask_provider_config: {
        provider: 'dify',
        mode: 'provider_only',
        config: { api_key: 'must-not-survive' },
      },
      tts_enabled: false,
      default_listen_mode_enabled: false,
      use_learner_language: false,
    });
    renderOpenSettings();

    await waitFor(() => {
      const latestProps = mockAskSettingsSection.mock.calls.at(-1)?.[0] as {
        askModelOptions: unknown[];
      };
      expect(latestProps.askModelOptions).toHaveLength(2);
    });
    const selectLive = mockAskSettingsSection.mock.calls.at(-1)?.[0]
      .onAskModelChange as (model: string) => void;
    act(() => selectLive('gemini-3.8-live'));
    await waitFor(() => {
      expect(mockAskSettingsSection.mock.calls.at(-1)?.[0]).toEqual(
        expect.objectContaining({
          isLiveVoiceFollowUp: true,
          liveVoice: 'Kore',
          resolvedAskProvider: 'llm',
        }),
      );
    });

    fireEvent.click(screen.getByLabelText('close-settings'));

    await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
    expect(mockSaveShifuDetail.mock.calls[0][0]).toEqual(
      expect.objectContaining({
        ask_model: 'gemini-3.8-live',
        ask_provider_config: {
          provider: 'llm',
          mode: 'provider_only',
          config: { live_voice: 'Kore' },
        },
      }),
    );
    await waitFor(() => {
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'creator_shifu_setting_save',
        expect.objectContaining({ follow_up_mode: 'live_voice' }),
      );
    });
  });

  const configureModelProvider = (modelIndex: string, provider: string) => {
    mockGetFollowUpModelCatalog.mockResolvedValue([
      { model: modelIndex, interaction_mode: 'text', voices: [] },
    ]);
    mockAskConfig.mockResolvedValue({
      providers: [
        { provider: 'llm', json_schema: { properties: {} } },
        ...['dify', 'coze'].map(name => ({
          provider: name,
          default_config: { api_key: 'default-secret', inputs: {} },
          json_schema: {
            properties: {
              api_key: { type: 'string' },
              inputs: { type: 'object' },
            },
            required: ['api_key'],
          },
        })),
      ],
    });
    mockGetShifuDetail.mockResolvedValue({
      bid: 'course-1',
      name: 'Private numbered model course',
      description: '',
      keywords: [],
      model: modelIndex,
      price: 1,
      avatar: '',
      temperature: 0,
      ask_model: modelIndex,
      ask_temperature: 0,
      follow_up_mode: 'text',
      ask_provider_config: {
        provider,
        mode: 'provider_only',
        config: { api_key: 'saved-secret', inputs: { lesson: 1 } },
      },
      tts_enabled: false,
      default_listen_mode_enabled: false,
      use_learner_language: false,
    });
    return () =>
      mockAskSettingsSection.mock.calls.at(-1)?.[0] as {
        resolvedAskProvider: string;
        onAskProviderChange: (provider: string) => void;
        setAskProviderConfig: React.Dispatch<
          React.SetStateAction<Record<string, unknown>>
        >;
        setAskProviderObjectInputs: React.Dispatch<
          React.SetStateAction<Record<string, string>>
        >;
      };
  };

  it.each(
    ['1', '3', '7'].flatMap(modelIndex =>
      ['dify', 'coze'].flatMap(provider =>
        ['provider', 'scalar', 'object'].map(edit => ({
          modelIndex,
          provider,
          edit,
        })),
      ),
    ),
  )(
    'saves $edit edits for $provider with model index $modelIndex',
    async ({ modelIndex, provider, edit }) => {
      const initialProvider = edit === 'provider' ? 'llm' : provider;
      const latestProps = configureModelProvider(modelIndex, initialProvider);
      renderOpenSettings();
      await screen.findByDisplayValue('Private numbered model course');
      await waitFor(() =>
        expect(latestProps().resolvedAskProvider).toBe(initialProvider),
      );
      act(() => {
        if (edit === 'provider') latestProps().onAskProviderChange(provider);
        if (edit === 'scalar')
          latestProps().setAskProviderConfig(previous => ({
            ...previous,
            api_key: 'edited-secret',
          }));
        if (edit === 'object')
          latestProps().setAskProviderObjectInputs({ inputs: '{"lesson":2}' });
      });
      expect(mockTrackEvent).not.toHaveBeenCalled();
      fireEvent.click(screen.getByLabelText('close-settings'));
      await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
      expect(mockSaveShifuDetail.mock.calls[0][0]).toEqual(
        expect.objectContaining({
          ask_provider_config: {
            provider,
            mode: 'provider_only',
            config: {
              api_key:
                edit === 'provider'
                  ? 'default-secret'
                  : edit === 'scalar'
                    ? 'edited-secret'
                    : 'saved-secret',
              inputs:
                edit === 'provider'
                  ? {}
                  : { lesson: edit === 'object' ? 2 : 1 },
            },
          },
        }),
      );
      await waitFor(() => expect(mockTrackEvent).toHaveBeenCalledTimes(1));
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'creator_shifu_setting_save',
        {
          shifu_bid: 'course-1',
          save_type: 'manual',
          tts_enabled: false,
          default_listen_mode_enabled: false,
          use_learner_language: false,
          follow_up_mode: 'text',
          price_tier: 'standard_paid',
          main_model_index: modelIndex,
          main_model_fallback: false,
          follow_up_model_fallback: false,
          follow_up_model_index: modelIndex,
        },
      );
      expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toMatch(
        /secret|api_key|inputs|dify|coze/,
      );
    },
  );

  it.each(['1', '3', '7'])(
    'preserves untouched %s provider settings when its provider metadata is missing',
    async modelIndex => {
      const latestProps = configureModelProvider(modelIndex, 'dify');
      mockAskConfig.mockResolvedValue({
        providers: [{ provider: 'llm', json_schema: { properties: {} } }],
      });
      renderOpenSettings();
      await screen.findByDisplayValue('Private numbered model course');
      await waitFor(() =>
        expect(latestProps().resolvedAskProvider).toBe('llm'),
      );
      fireEvent.click(screen.getByLabelText('close-settings'));
      await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
      expect(mockSaveShifuDetail.mock.calls[0][0]).toEqual(
        expect.objectContaining({
          ask_provider_config: {
            provider: 'dify',
            mode: 'provider_only',
            config: { api_key: 'saved-secret', inputs: { lesson: 1 } },
          },
        }),
      );
    },
  );

  it.each(['required', 'invalid_json'])(
    'validates %s errors in edited model provider settings before saving',
    async error => {
      const latestProps = configureModelProvider('1', 'dify');
      renderOpenSettings();
      await screen.findByDisplayValue('Private numbered model course');
      await waitFor(() =>
        expect(latestProps().resolvedAskProvider).toBe('dify'),
      );
      act(() => {
        if (error === 'required')
          latestProps().setAskProviderConfig({ api_key: '' });
        else latestProps().setAskProviderObjectInputs({ inputs: '{' });
      });
      fireEvent.click(screen.getByLabelText('close-settings'));
      await waitFor(() => expect(mockToast).toHaveBeenCalled());
      expect(mockSaveShifuDetail).not.toHaveBeenCalled();
      expect(mockTrackEvent).not.toHaveBeenCalled();
      expect(screen.getByLabelText('close-settings')).toBeInTheDocument();
    },
  );

  it('preserves external provider and unsaved fields across a Live round trip', async () => {
    mockGetFollowUpModelCatalog.mockResolvedValue([
      {
        model: '1',
        display_name: 'Text',
        interaction_mode: 'text',
        voices: [],
      },
      {
        model: 'live-model',
        display_name: 'Live',
        interaction_mode: 'live_voice',
        voices: [
          { voice_id: 'Kore', style: 'Firm' },
          { voice_id: 'Puck', style: 'Upbeat' },
        ],
      },
    ]);
    mockAskConfig.mockResolvedValue({
      providers: [
        { provider: 'llm', json_schema: { properties: {} } },
        {
          provider: 'dify',
          json_schema: {
            properties: {
              api_key: { type: 'string' },
              inputs: { type: 'object' },
            },
            required: ['api_key'],
          },
        },
      ],
    });
    mockGetShifuDetail.mockResolvedValue({
      bid: 'course-1',
      name: 'Private course name',
      description: 'Private course description',
      keywords: [],
      model: '',
      price: 1,
      avatar: '',
      temperature: 0,
      system_prompt: '',
      ask_model: '1',
      ask_temperature: 0,
      ask_provider_config: {
        provider: 'dify',
        mode: 'provider_only',
        config: { api_key: 'saved-secret' },
      },
      tts_enabled: false,
      default_listen_mode_enabled: false,
      use_learner_language: false,
    });
    renderOpenSettings();
    const latestProps = () =>
      mockAskSettingsSection.mock.calls.at(-1)?.[0] as {
        onAskModelChange: (model: string) => void;
        onLiveVoiceChange: (voice: string) => void;
        setAskProviderConfig: (config: Record<string, unknown>) => void;
        setAskProviderObjectInputs: (inputs: Record<string, string>) => void;
        resolvedAskProvider: string;
        liveVoice: string;
      };
    await waitFor(() => expect(latestProps().resolvedAskProvider).toBe('dify'));
    act(() => {
      latestProps().setAskProviderConfig({ api_key: 'edited-secret' });
      latestProps().setAskProviderObjectInputs({ inputs: '{"lesson":1}' });
    });
    act(() => latestProps().onAskModelChange('live-model'));
    expect(latestProps().resolvedAskProvider).toBe('llm');
    act(() => latestProps().onLiveVoiceChange('Puck'));
    act(() => latestProps().onAskModelChange('1'));
    expect(latestProps().resolvedAskProvider).toBe('dify');
    act(() => latestProps().onAskModelChange('live-model'));
    expect(latestProps().liveVoice).toBe('Puck');
    act(() => latestProps().onAskModelChange('1'));
    fireEvent.click(screen.getByLabelText('close-settings'));
    await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
    expect(mockSaveShifuDetail.mock.calls[0][0]).toEqual(
      expect.objectContaining({
        ask_model: '1',
        ask_provider_config: {
          provider: 'dify',
          mode: 'provider_only',
          config: { api_key: 'edited-secret', inputs: { lesson: 1 } },
        },
      }),
    );
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_shifu_setting_save',
      expect.objectContaining({ follow_up_mode: 'text' }),
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'edited-secret',
    );
  });

  it('preserves the selected Live voice across a temporary text-model switch', async () => {
    mockGetFollowUpModelCatalog.mockResolvedValue([
      {
        model: '1',
        display_name: 'Text model',
        interaction_mode: 'text',
        allowed_roles: ['main', 'follow_up'],
        billing_mode: 'billable',
        voices: [],
        is_default: true,
      },
      {
        model: 'gemini-3.8-live',
        display_name: 'Gemini Live',
        interaction_mode: 'live_voice',
        allowed_roles: ['follow_up'],
        billing_mode: 'free_preview',
        voices: [
          { voice_id: 'Kore', style: 'Firm' },
          { voice_id: 'Puck', style: 'Upbeat' },
        ],
      },
    ]);
    mockGetShifuDetail.mockResolvedValue({
      bid: 'course-1',
      name: 'Private course name',
      description: 'Private course description',
      keywords: [],
      model: '',
      price: 1,
      avatar: '',
      temperature: 0,
      system_prompt: '',
      ask_model: 'gemini-3.8-live',
      ask_temperature: 0,
      ask_provider_config: {
        provider: 'llm',
        mode: 'provider_only',
        config: { live_voice: 'Puck' },
      },
      tts_enabled: false,
      default_listen_mode_enabled: false,
      use_learner_language: false,
    });
    renderOpenSettings();

    await waitFor(() => {
      expect(mockAskSettingsSection.mock.calls.at(-1)?.[0]).toEqual(
        expect.objectContaining({
          isLiveVoiceFollowUp: true,
          liveVoice: 'Puck',
        }),
      );
    });

    const selectText = mockAskSettingsSection.mock.calls.at(-1)?.[0]
      .onAskModelChange as (model: string) => void;
    act(() => selectText('1'));
    await waitFor(() => {
      expect(mockAskSettingsSection.mock.calls.at(-1)?.[0]).toEqual(
        expect.objectContaining({ isLiveVoiceFollowUp: false }),
      );
    });

    const selectLive = mockAskSettingsSection.mock.calls.at(-1)?.[0]
      .onAskModelChange as (model: string) => void;
    act(() => selectLive('gemini-3.8-live'));
    await waitFor(() => {
      expect(mockAskSettingsSection.mock.calls.at(-1)?.[0]).toEqual(
        expect.objectContaining({
          isLiveVoiceFollowUp: true,
          liveVoice: 'Puck',
        }),
      );
    });

    const selectTextAgain = mockAskSettingsSection.mock.calls.at(-1)?.[0]
      .onAskModelChange as (model: string) => void;
    act(() => selectTextAgain('1'));
    await waitFor(() => {
      expect(mockAskSettingsSection.mock.calls.at(-1)?.[0]).toEqual(
        expect.objectContaining({ isLiveVoiceFollowUp: false }),
      );
    });

    fireEvent.click(screen.getByLabelText('close-settings'));

    await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
    expect(mockSaveShifuDetail.mock.calls[0][0]).toEqual(
      expect.objectContaining({
        ask_model: '1',
        ask_provider_config: {
          provider: 'llm',
          mode: 'provider_only',
          config: { live_voice: 'Puck' },
        },
      }),
    );
  });
});

describe('ShifuSetting numbered model persistence', () => {
  it('saves a text model index over a retained Live model without exposing or overwriting it', async () => {
    jest.clearAllMocks();
    mockEnvState.billingEnabled = 'false';
    mockGetFollowUpModelCatalog.mockResolvedValue([
      { model: 'gemini-3.8-live', interaction_mode: 'live_voice', voices: [] },
    ]);
    mockTtsConfig.mockResolvedValue({ providers: [], model_options: [] });
    mockAskConfig.mockResolvedValue({ providers: [] });
    mockSaveShifuDetail.mockResolvedValue(undefined);
    mockTrackEvent.mockImplementation(() => undefined);
    mockGetShifuDetail.mockResolvedValue({
      bid: 'course-1',
      name: 'Numbered model course',
      description: '',
      model: '7',
      ask_model: '1',
      follow_up_mode: 'text',
      price: 1,
      ask_provider_config: {
        provider: 'llm',
        mode: 'provider_only',
        config: {},
      },
    });
    renderOpenSettings();
    await screen.findByDisplayValue('Numbered model course');
    await waitFor(() =>
      expect(mockAskSettingsSection.mock.calls.at(-1)?.[0]).toEqual(
        expect.objectContaining({
          isLiveVoiceFollowUp: false,
          askModelIndex: '1',
        }),
      ),
    );
    act(() =>
      mockAskSettingsSection.mock.calls.at(-1)?.[0].onAskModelIndexChange('3'),
    );
    fireEvent.click(screen.getByLabelText('close-settings'));
    await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
    expect(mockSaveShifuDetail.mock.calls[0][0]).toEqual(
      expect.objectContaining({
        ask_model: '3',
      }),
    );
    const modelFields = Object.keys(
      mockSaveShifuDetail.mock.calls[0][0],
    ).filter(
      key => key === 'model' || key === 'ask_model' || key.includes('llm'),
    );
    expect(modelFields).toEqual(['ask_model']);
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_shifu_setting_save',
      expect.objectContaining({
        main_model_index: '7',
        main_model_fallback: false,
        follow_up_model_fallback: false,
        follow_up_model_index: '3',
        follow_up_mode: 'text',
      }),
    );
  });
});

describe('ShifuSetting Live-to-text availability', () => {
  const liveCourse = {
    bid: 'course-1',
    name: 'Private Live course',
    description: '',
    model: '1',
    ask_model: 'gemini-3.8-live',
    follow_up_mode: 'live_voice',
    price: 1,
    ask_provider_config: {
      provider: 'llm',
      mode: 'provider_only',
      config: { live_voice: 'Puck' },
    },
  };
  const latest = () => mockAskSettingsSection.mock.calls.at(-1)?.[0];
  const openLive = async () => {
    renderOpenSettings();
    await screen.findByDisplayValue('Private Live course');
    await waitFor(() => expect(latest().isLiveVoiceFollowUp).toBe(true));
  };
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetCourseModelOptions.mockReset();
    mockEnvState.billingEnabled = 'false';
    mockTtsConfig.mockResolvedValue({ providers: [], model_options: [] });
    mockAskConfig.mockResolvedValue({ providers: [] });
    mockSaveShifuDetail.mockResolvedValue(undefined);
    mockTrackEvent.mockImplementation(() => undefined);
    mockGetShifuDetail.mockResolvedValue(liveCourse);
    mockGetFollowUpModelCatalog.mockResolvedValue([
      { model: 'gemini-3.8-live', interaction_mode: 'live_voice', voices: [] },
    ]);
  });
  it.each(['unavailable', 'missing', 'failure'])(
    'keeps Live when default model availability is %s',
    async status => {
      if (status === 'failure')
        mockGetCourseModelOptions.mockRejectedValue(
          new Error('private provider error'),
        );
      else
        mockGetCourseModelOptions.mockResolvedValue(
          status === 'missing' ? [] : [{ index: '1', available: false }],
        );
      await openLive();
      await act(async () => latest().onFollowUpModeChange('text'));
      expect(latest()).toEqual(
        expect.objectContaining({
          isLiveVoiceFollowUp: true,
          askModelIndex: null,
          checkingTextMode: false,
        }),
      );
      expect(mockToast).toHaveBeenCalledWith({
        title: 'module.shifuSetting.modelOptions.unavailable',
        variant: 'destructive',
      });
      expect(mockSaveShifuDetail).not.toHaveBeenCalled();
      expect(mockTrackEvent).not.toHaveBeenCalled();
      fireEvent.click(screen.getByLabelText('close-settings'));
      await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
      expect(mockSaveShifuDetail.mock.calls[0][0]).not.toHaveProperty(
        'ask_model',
      );
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'creator_shifu_setting_save',
        expect.objectContaining({
          follow_up_mode: 'live_voice',
          follow_up_model_index: 'not_applicable',
        }),
      );
      expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toMatch(
        /gemini|private provider error|Private Live course/,
      );
    },
  );
  it.each([false, true])(
    'saves the available default model even if tracking fails=%s',
    async trackingFails => {
      mockGetCourseModelOptions.mockResolvedValue([
        { index: '1', available: true },
      ]);
      if (trackingFails)
        mockTrackEvent.mockImplementation(() => {
          throw new Error('analytics unavailable');
        });
      await openLive();
      await act(async () => latest().onFollowUpModeChange('text'));
      expect(latest()).toEqual(
        expect.objectContaining({
          isLiveVoiceFollowUp: false,
          askModelIndex: '1',
        }),
      );
      expect(mockTrackEvent).not.toHaveBeenCalled();
      fireEvent.click(screen.getByLabelText('close-settings'));
      await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
      expect(mockSaveShifuDetail.mock.calls[0][0].ask_model).toBe('1');
      expect(mockTrackEvent).toHaveBeenCalledTimes(1);
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'creator_shifu_setting_save',
        expect.objectContaining({
          follow_up_mode: 'text',
          follow_up_model_index: '1',
        }),
      );
      expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toMatch(
        /gemini|Private Live course|live_voice/,
      );
    },
  );
  it('ignores an availability response after the dialog closes', async () => {
    let resolveOptions!: (options: unknown[]) => void;
    mockGetCourseModelOptions.mockReturnValue(
      new Promise(resolve => {
        resolveOptions = resolve;
      }),
    );
    await openLive();
    let switching!: Promise<void>;
    act(() => {
      switching = latest().onFollowUpModeChange('text');
    });
    expect(latest().checkingTextMode).toBe(true);
    expect(latest().isLiveVoiceFollowUp).toBe(true);
    fireEvent.click(screen.getByLabelText('close-settings'));
    await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
    await act(async () => {
      resolveOptions([{ index: '1', available: true }]);
      await switching;
    });
    expect(mockSaveShifuDetail.mock.calls[0][0]).not.toHaveProperty(
      'ask_model',
    );
    expect(latest().isLiveVoiceFollowUp).toBe(true);
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
  });
  it('rechecks the remembered model index instead of silently replacing it with the default', async () => {
    mockGetShifuDetail.mockResolvedValue({
      ...liveCourse,
      ask_model: '3',
      follow_up_mode: 'text',
    });
    mockGetCourseModelOptions.mockResolvedValue([
      { index: '1', available: true },
      { index: '3', available: false },
    ]);
    renderOpenSettings();
    await screen.findByDisplayValue('Private Live course');
    await act(async () => latest().onFollowUpModeChange('live_voice'));
    expect(latest().isLiveVoiceFollowUp).toBe(true);
    await act(async () => latest().onFollowUpModeChange('text'));
    expect(latest().isLiveVoiceFollowUp).toBe(true);
    expect(mockToast).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).not.toHaveBeenCalled();
  });
});

describe('ShifuSetting compatibility fallback and explicit selection', () => {
  const main = () => mockMainModelSelector.mock.calls.at(-1)?.[0];
  const followUp = () => mockAskSettingsSection.mock.calls.at(-1)?.[0];
  const submitSettings = (submission: string) => {
    if (submission === 'close') {
      fireEvent.click(screen.getByLabelText('close-settings'));
      return;
    }
    // Supply the existing schema's required bounds so native submission
    // reaches its success callback instead of passing cancellation tests
    // merely because unrelated full-form validation failed.
    act(() => {
      const form = mockFormMethods.mock.calls.at(-1)?.[0];
      form.setValue('temperature_min', 0);
      form.setValue('temperature_max', 2);
    });
    fireEvent.submit(
      screen.getByDisplayValue('Compatibility course').closest('form')!,
    );
  };
  const detail = {
    bid: 'course-1',
    name: 'Compatibility course',
    description: '',
    keywords: [],
    model: '1',
    model_fallback: true,
    model_display_name: 'Default label',
    ask_model: '1',
    ask_model_fallback: true,
    ask_model_display_name: 'Default label',
    follow_up_mode: 'text',
    price: 0,
    temperature: 0,
    ask_provider_config: { provider: 'llm', mode: 'provider_only', config: {} },
  };
  const open = async () => {
    const result = renderOpenSettings();
    await screen.findByDisplayValue('Compatibility course');
    await waitFor(() => expect(main().value).toBe('1'));
    return result;
  };
  beforeEach(() => {
    jest.clearAllMocks();
    mockCurrentShifu.readonly = false;
    mockEnvState.billingEnabled = 'false';
    mockTtsConfig.mockResolvedValue({ providers: [], model_options: [] });
    mockAskConfig.mockResolvedValue({ providers: [] });
    mockTrackEvent.mockImplementation(() => undefined);
    mockGetShifuDetail.mockResolvedValue(detail);
    mockSaveShifuDetail.mockResolvedValue(detail);
    mockGetFollowUpModelCatalog.mockResolvedValue([
      {
        model: '1',
        interaction_mode: 'text',
        display_name: 'Default label',
        voices: [],
      },
    ]);
  });
  it('shows effective fallback selections and omits untouched model fields on unrelated saves', async () => {
    await open();
    expect(main()).toEqual(
      expect.objectContaining({
        value: '1',
        displayName: 'Default label',
      }),
    );
    expect(followUp()).toEqual(expect.objectContaining({ askModelIndex: '1' }));
    expect(mockSaveShifuDetail).not.toHaveBeenCalled();
    fireEvent.change(screen.getByDisplayValue('Compatibility course'), {
      target: { value: 'Renamed course' },
    });
    fireEvent.click(screen.getByLabelText('close-settings'));
    await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
    expect(mockSaveShifuDetail.mock.calls[0][0]).not.toHaveProperty('model');
    expect(mockSaveShifuDetail.mock.calls[0][0]).not.toHaveProperty(
      'ask_model',
    );
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_shifu_setting_save',
      expect.objectContaining({
        main_model_index: '1',
        follow_up_model_index: '1',
        main_model_fallback: true,
        follow_up_model_fallback: true,
      }),
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toMatch(
      /Default label|Renamed course|Compatibility course/,
    );
  });
  it.each(['main', 'followUp'])(
    'writes only the explicitly re-selected default for %s',
    async field => {
      mockSaveShifuDetail.mockResolvedValue({
        ...detail,
        ...(field === 'main'
          ? { model_fallback: false }
          : { ask_model_fallback: false }),
      });
      await open();
      act(() =>
        field === 'main'
          ? main().onChange('1')
          : followUp().onAskModelIndexChange('1'),
      );
      fireEvent.click(screen.getByLabelText('close-settings'));
      await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
      const payload = mockSaveShifuDetail.mock.calls[0][0];
      expect(payload[field === 'main' ? 'model' : 'ask_model']).toBe('1');
      expect(payload).not.toHaveProperty(
        field === 'main' ? 'ask_model' : 'model',
      );
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'creator_shifu_setting_save',
        expect.objectContaining({
          main_model_fallback: field !== 'main',
          follow_up_model_fallback: field !== 'followUp',
        }),
      );
    },
  );
  it.each(['main', 'followUp'])(
    'preserves a newer %s selection while an earlier save completes',
    async field => {
      const saving = createDeferred<typeof detail>();
      mockSaveShifuDetail.mockReturnValueOnce(saving.promise);
      await open();
      const choose = (index: string) =>
        field === 'main'
          ? main().onChange(index)
          : followUp().onAskModelIndexChange(index);
      act(() => choose('3'));
      fireEvent.click(screen.getByLabelText('close-settings'));
      await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
      act(() => choose('7'));
      await act(async () => {
        saving.resolve({
          ...detail,
          ...(field === 'main'
            ? { model: '3', model_fallback: false }
            : { ask_model: '3', ask_model_fallback: false }),
        });
        await saving.promise;
      });
      expect(field === 'main' ? main().value : followUp().askModelIndex).toBe(
        '7',
      );
      expect(screen.getByLabelText('close-settings')).toBeInTheDocument();
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'creator_shifu_setting_save',
        expect.objectContaining({
          [field === 'main' ? 'main_model_index' : 'follow_up_model_index']:
            '3',
        }),
      );
      mockSaveShifuDetail.mockResolvedValue({
        ...detail,
        ...(field === 'main'
          ? { model: '7', model_fallback: false }
          : { ask_model: '7', ask_model_fallback: false }),
      });
      fireEvent.click(screen.getByLabelText('close-settings'));
      await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(2));
      expect(
        mockSaveShifuDetail.mock.calls[1][0][
          field === 'main' ? 'model' : 'ask_model'
        ],
      ).toBe('7');
    },
  );
  it('retains an explicit model selection after a rejected save for retry', async () => {
    mockSaveShifuDetail.mockRejectedValueOnce(new Error('save rejected'));
    await open();
    act(() => main().onChange('3'));
    fireEvent.click(screen.getByLabelText('close-settings'));
    await waitFor(() => expect(mockToast).toHaveBeenCalled());
    expect(mockTrackEvent).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('close-settings'));
    await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(2));
    expect(mockSaveShifuDetail.mock.calls[1][0].model).toBe('3');
  });
  it('reports the effective server result if a numbered configuration disappeared before saving', async () => {
    await open();
    act(() => main().onChange('3'));
    fireEvent.click(screen.getByLabelText('close-settings'));
    await waitFor(() => expect(mockTrackEvent).toHaveBeenCalledTimes(1));
    expect(mockSaveShifuDetail.mock.calls[0][0].model).toBe('3');
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_shifu_setting_save',
      expect.objectContaining({
        main_model_index: '1',
        main_model_fallback: true,
      }),
    );
  });
  it('uses model 1 when a remembered text number was removed before switching from Live', async () => {
    mockGetShifuDetail.mockResolvedValue({
      ...detail,
      ask_model: '3',
      ask_model_fallback: false,
    });
    mockGetFollowUpModelCatalog.mockResolvedValue([
      { model: 'gemini-3.8-live', interaction_mode: 'live_voice', voices: [] },
    ]);
    mockGetCourseModelOptions.mockResolvedValue([
      { index: '1', display_name: 'Default label', available: true },
    ]);
    await open();
    await act(async () => followUp().onFollowUpModeChange('live_voice'));
    expect(followUp().isLiveVoiceFollowUp).toBe(true);
    await act(async () => followUp().onFollowUpModeChange('text'));
    expect(followUp().askModelIndex).toBe('1');
    fireEvent.click(screen.getByLabelText('close-settings'));
    await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
    expect(mockSaveShifuDetail.mock.calls[0][0].ask_model).toBe('1');
  });
  it('omits unchanged choices on autosave without changing the fallback flags', async () => {
    await open();
    jest.useFakeTimers();
    try {
      fireEvent.change(screen.getByDisplayValue('Compatibility course'), {
        target: { value: 'Autosaved course' },
      });
      await act(async () => {
        jest.advanceTimersByTime(3000);
      });
      expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1);
      expect(mockSaveShifuDetail.mock.calls[0][0]).not.toHaveProperty('model');
      expect(mockSaveShifuDetail.mock.calls[0][0]).not.toHaveProperty(
        'ask_model',
      );
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'creator_shifu_setting_save',
        expect.objectContaining({
          save_type: 'auto',
          main_model_fallback: true,
          follow_up_model_fallback: true,
        }),
      );
    } finally {
      jest.useRealTimers();
    }
  });
  it.each([false, true])(
    'previews the saved raw selection unless the follow-up selection was edited=%s',
    async edited => {
      mockAskPreview.mockResolvedValue({
        answer: 'Private answer',
        provider: 'llm',
      });
      await open();
      act(() => {
        followUp().setAskPreviewQuery('Private question');
        if (edited) followUp().onAskModelIndexChange('3');
      });
      await act(async () => followUp().handleAskPreview());
      expect(mockAskPreview).toHaveBeenCalledTimes(1);
      if (edited) expect(mockAskPreview.mock.calls[0][0].ask_model).toBe('3');
      else
        expect(mockAskPreview.mock.calls[0][0]).not.toHaveProperty('ask_model');
      expect(mockSaveShifuDetail).not.toHaveBeenCalled();
      expect(mockTrackEvent).not.toHaveBeenCalled();
    },
  );
  it.each(['main', 'followUp'])(
    'serializes overlapping %s saves so older writes cannot win',
    async field => {
      const firstSave = createDeferred<typeof detail>();
      const secondSave = createDeferred<typeof detail>();
      mockSaveShifuDetail
        .mockReturnValueOnce(firstSave.promise)
        .mockReturnValueOnce(secondSave.promise);
      await open();
      const choose = (index: string) =>
        field === 'main'
          ? main().onChange(index)
          : followUp().onAskModelIndexChange(index);
      act(() => choose('3'));
      fireEvent.click(screen.getByLabelText('close-settings'));
      await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
      act(() => choose('7'));
      fireEvent.click(screen.getByLabelText('close-settings'));
      await act(async () => {});
      // Request B waits even if its response could otherwise finish first.
      expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1);
      await act(async () => {
        firstSave.resolve({
          ...detail,
          ...(field === 'main'
            ? { model: '3', model_fallback: false }
            : { ask_model: '3', ask_model_fallback: false }),
        });
        await firstSave.promise;
      });
      await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(2));
      expect(
        mockSaveShifuDetail.mock.calls[1][0][
          field === 'main' ? 'model' : 'ask_model'
        ],
      ).toBe('7');
      expect(field === 'main' ? main().value : followUp().askModelIndex).toBe(
        '7',
      );
      await act(async () => {
        secondSave.resolve({
          ...detail,
          ...(field === 'main'
            ? { model: '7', model_fallback: false }
            : { ask_model: '7', ask_model_fallback: false }),
        });
        await secondSave.promise;
      });
      expect(
        mockTrackEvent.mock.calls.map(
          call =>
            call[1][
              field === 'main' ? 'main_model_index' : 'follow_up_model_index'
            ],
        ),
      ).toEqual(['3', '7']);
    },
  );
  it('does not resend an acknowledged model choice from a queued unrelated save', async () => {
    const firstSave = createDeferred<typeof detail>();
    mockSaveShifuDetail.mockReturnValueOnce(firstSave.promise);
    await open();
    act(() => main().onChange('3'));
    fireEvent.click(screen.getByLabelText('close-settings'));
    await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByDisplayValue('Compatibility course'), {
      target: { value: 'Queued title' },
    });
    fireEvent.click(screen.getByLabelText('close-settings'));
    await act(async () => {});
    expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1);
    await act(async () => {
      firstSave.resolve({ ...detail, model: '3', model_fallback: false });
      await firstSave.promise;
    });
    await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(2));
    expect(mockSaveShifuDetail.mock.calls[1][0]).not.toHaveProperty('model');
    expect(mockSaveShifuDetail.mock.calls[1][0]).not.toHaveProperty(
      'ask_model',
    );
    expect(mockSaveShifuDetail.mock.calls[1][0].name).toBe('Queued title');
  });
  it.each([
    ['main', 'close'],
    ['followUp', 'close'],
    ['main', 'submit'],
    ['followUp', 'submit'],
  ])(
    'captures the latest %s choice when it changes during async %s validation',
    async (field, submission) => {
      await open();
      submitSettings(submission);
      // Both submit paths await validation before their success callbacks.
      expect(mockSaveShifuDetail).not.toHaveBeenCalled();
      act(() =>
        field === 'main'
          ? main().onChange('3')
          : followUp().onAskModelIndexChange('3'),
      );
      await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
      expect(
        mockSaveShifuDetail.mock.calls[0][0][
          field === 'main' ? 'model' : 'ask_model'
        ],
      ).toBe('3');
    },
  );
  it.each([
    ['close', 'before'],
    ['submit', 'before'],
    ['submit', 'after'],
  ])(
    'cancels %s started %s a different course begins loading',
    async (submission, timing) => {
      const nextDetail = createDeferred<typeof detail>();
      const onSave = jest.fn();
      const { rerender } = render(
        <ShifuSettingDialog
          shifuId='course-1'
          openSignal='course-context-test'
          onSave={onSave}
        />,
      );
      await screen.findByDisplayValue('Compatibility course');
      act(() => main().onChange('3'));
      if (timing === 'before') submitSettings(submission);
      expect(mockSaveShifuDetail).not.toHaveBeenCalled();

      mockGetShifuDetail.mockReturnValueOnce(nextDetail.promise);
      rerender(
        <ShifuSettingDialog
          shifuId='course-2'
          openSignal='course-context-test'
          onSave={onSave}
        />,
      );
      if (timing === 'after') submitSettings(submission);
      await act(async () => {});

      expect(mockGetShifuDetail).toHaveBeenLastCalledWith({
        shifu_bid: 'course-2',
      });
      expect(mockSaveShifuDetail).not.toHaveBeenCalled();
      expect(mockTrackEvent).not.toHaveBeenCalled();
      expect(onSave).not.toHaveBeenCalled();
      await act(async () => {
        nextDetail.resolve({ ...detail, bid: 'course-2', name: 'Next course' });
        await nextDetail.promise;
      });
      expect(screen.getByDisplayValue('Next course')).toBeInTheDocument();
      expect(screen.getByLabelText('close-settings')).toBeInTheDocument();
    },
  );
});
