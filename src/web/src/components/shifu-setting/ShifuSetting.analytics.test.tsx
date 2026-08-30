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
  useBillingOverview: () => ({ data: undefined }),
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
jest.mock('@/components/shifu-setting/AskSettingsSection', () => () => null);
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
});
