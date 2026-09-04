import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import ShifuSettingDialog from './ShifuSetting';

const mockTtsConfig = jest.fn();
const mockAskConfig = jest.fn();
const mockGetShifuDetail = jest.fn();
const mockSaveShifuDetail = jest.fn();
const mockTrackEvent = jest.fn();
const mockToast = jest.fn();
const mockGetFollowUpModelCatalog = jest.fn();
const mockAskSettingsSection = jest.fn();
const mockBillingOverview = { debug_allowed: undefined as boolean | undefined };

const mockEnvState = {
  defaultLlmModel: '',
  currencySymbol: '¥',
  billingEnabled: 'false',
};

jest.mock('sse.js', () => ({ SSE: jest.fn() }));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    ttsConfig: (...args: unknown[]) => mockTtsConfig(...args),
    askConfig: (...args: unknown[]) => mockAskConfig(...args),
    getShifuDetail: (...args: unknown[]) => mockGetShifuDetail(...args),
    saveShifuDetail: (...args: unknown[]) => mockSaveShifuDetail(...args),
  },
}));

jest.mock('@/store', () => ({
  useShifu: () => ({
    currentShifu: { bid: 'course-1', readonly: false },
    models: [],
  }),
  useUserStore: Object.assign(jest.fn(), {
    getState: () => ({ getToken: () => '' }),
  }),
}));

jest.mock('@/c-store', () => ({
  useEnvStore: (selector: (state: typeof mockEnvState) => unknown) =>
    selector(mockEnvState),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
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
jest.mock('@/components/shifu-setting/AskSettingsSection', () => ({
  __esModule: true,
  default: (props: Record<string, unknown>) => {
    mockAskSettingsSection(props);
    return null;
  },
}));
jest.mock(
  '@/components/shifu-setting/MiniMaxVoiceCloneDialog',
  () => () => null,
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
    mockAskConfig.mockResolvedValue({ providers: [] });
    mockSaveShifuDetail.mockResolvedValue(undefined);
    mockTrackEvent.mockImplementation(() => undefined);
    mockGetFollowUpModelCatalog.mockResolvedValue([]);
    mockEnvState.billingEnabled = 'false';
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

  it('emits the exact allowlist only after the settings API succeeds', async () => {
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
        },
      );
    });
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent.mock.calls[0][1]).not.toHaveProperty('name');
    expect(mockTrackEvent.mock.calls[0][1]).not.toHaveProperty('description');
    expect(mockTrackEvent.mock.calls[0][1]).not.toHaveProperty('system_prompt');
    expect(mockTrackEvent.mock.calls[0][1]).not.toHaveProperty(
      'ask_provider_config',
    );
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it('emits nothing when the settings API fails', async () => {
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
  });

  it('completes the successful save flow when analytics throws', async () => {
    mockTrackEvent.mockImplementation(() => {
      throw new Error('analytics unavailable');
    });
    const { onSave } = renderOpenSettings();

    await screen.findByDisplayValue('Private course name');
    fireEvent.click(screen.getByLabelText('close-settings'));

    await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(screen.queryByLabelText('close-settings')).not.toBeInTheDocument();
  });

  it('keeps text debug gated while exposing Live and the saved default model', async () => {
    mockEnvState.billingEnabled = 'true';
    mockGetFollowUpModelCatalog.mockResolvedValue([
      {
        model: 'text-model',
        display_name: 'Text model',
        interaction_mode: 'text',
        allowed_roles: ['main', 'follow_up'],
        billing_mode: 'billable',
        voices: [],
        is_default: true,
      },
      {
        model: 'gemini-3.1-flash-live-preview',
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
        expect.objectContaining({ value: 'text-model', disabled: false }),
        expect.objectContaining({
          value: 'gemini-3.1-flash-live-preview',
          disabled: false,
        }),
      ]);
    });
  });

  it.each(
    [false, undefined].flatMap(debugAllowed => [
      { debugAllowed, savedModel: 'saved-text', markedDefault: false },
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
          model: 'saved-text',
          display_name: 'Saved',
          interaction_mode: 'text',
          voices: [],
          is_default: markedDefault,
        },
        {
          model: 'other-text',
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
            disabled: item.model !== 'saved-text',
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
          ask_model: savedModel,
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
        },
      );
      expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    },
  );

  it('does not save while the follow-up catalog is unresolved', async () => {
    const catalog = createDeferred<unknown[]>();
    mockGetFollowUpModelCatalog.mockReturnValue(catalog.promise);
    renderOpenSettings();
    await screen.findByDisplayValue('Private course name');

    fireEvent.click(screen.getByLabelText('close-settings'));

    expect(mockSaveShifuDetail).not.toHaveBeenCalled();
    expect(screen.getByLabelText('close-settings')).toBeInTheDocument();

    await act(async () => {
      catalog.resolve([]);
      await catalog.promise;
    });
    fireEvent.click(screen.getByLabelText('close-settings'));
    await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
  });

  it.each(['unavailable', 'failed'] as const)(
    'preserves an existing Live config when the catalog is %s',
    async catalogState => {
      if (catalogState === 'failed') {
        mockGetFollowUpModelCatalog.mockRejectedValue(
          new Error('catalog unavailable'),
        );
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
          ask_model: 'opaque-existing-model-id',
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
        model: 'text-model',
        display_name: 'Text model',
        interaction_mode: 'text',
        allowed_roles: ['main', 'follow_up'],
        billing_mode: 'billable',
        voices: [],
        is_default: true,
      },
      {
        model: 'gemini-3.1-flash-live-preview',
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
      ask_model: 'text-model',
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
    act(() => selectLive('gemini-3.1-flash-live-preview'));
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
        ask_model: 'gemini-3.1-flash-live-preview',
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

  it('preserves external provider and unsaved fields across a Live round trip', async () => {
    mockGetFollowUpModelCatalog.mockResolvedValue([
      {
        model: 'text-model',
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
      ask_model: 'text-model',
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
    act(() => latestProps().onAskModelChange('text-model'));
    expect(latestProps().resolvedAskProvider).toBe('dify');
    act(() => latestProps().onAskModelChange('live-model'));
    expect(latestProps().liveVoice).toBe('Puck');
    act(() => latestProps().onAskModelChange('text-model'));
    fireEvent.click(screen.getByLabelText('close-settings'));
    await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
    expect(mockSaveShifuDetail.mock.calls[0][0]).toEqual(
      expect.objectContaining({
        ask_model: 'text-model',
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
        model: 'text-model',
        display_name: 'Text model',
        interaction_mode: 'text',
        allowed_roles: ['main', 'follow_up'],
        billing_mode: 'billable',
        voices: [],
        is_default: true,
      },
      {
        model: 'gemini-3.1-flash-live-preview',
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
      ask_model: 'gemini-3.1-flash-live-preview',
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
    act(() => selectText('text-model'));
    await waitFor(() => {
      expect(mockAskSettingsSection.mock.calls.at(-1)?.[0]).toEqual(
        expect.objectContaining({ isLiveVoiceFollowUp: false }),
      );
    });

    const selectLive = mockAskSettingsSection.mock.calls.at(-1)?.[0]
      .onAskModelChange as (model: string) => void;
    act(() => selectLive('gemini-3.1-flash-live-preview'));
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
    act(() => selectTextAgain('text-model'));
    await waitFor(() => {
      expect(mockAskSettingsSection.mock.calls.at(-1)?.[0]).toEqual(
        expect.objectContaining({ isLiveVoiceFollowUp: false }),
      );
    });

    fireEvent.click(screen.getByLabelText('close-settings'));

    await waitFor(() => expect(mockSaveShifuDetail).toHaveBeenCalledTimes(1));
    expect(mockSaveShifuDetail.mock.calls[0][0]).toEqual(
      expect.objectContaining({
        ask_model: 'text-model',
        ask_provider_config: {
          provider: 'llm',
          mode: 'provider_only',
          config: { live_voice: 'Puck' },
        },
      }),
    );
  });
});
