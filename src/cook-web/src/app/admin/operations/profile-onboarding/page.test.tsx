import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import api from '@/api';
import { streamProfileOnboardingRuntime } from '@/lib/profileOnboardingSse';
import ProfileOnboardingAdminPage from './page';
import {
  PROFILE_CONFIG_LOAD_RETRY_ATTEMPT_EVENT,
  PROFILE_CONFIG_LOAD_RETRY_RESULT_EVENT,
  PROFILE_DIRTY_NAVIGATION_DECISION_EVENT,
  PROFILE_DIRTY_NAVIGATION_SAVE_RESULT_EVENT,
  PROFILE_DIRTY_NAVIGATION_SHOWN_EVENT,
  PROFILE_PROMPT_GENERATE_ATTEMPT_EVENT,
  PROFILE_PROMPT_GENERATE_RESULT_EVENT,
} from './useProfileOnboardingAdminController';

const mockToast = jest.fn();
const mockTrackEvent = jest.fn();
const mockPush = jest.fn();
const RUN_MOCKED_PREVIEW_LABEL = 'run mocked preview';
const DOCUMENT = '?[%{{research_topic}}...最近在关注什么？]';
const PROMPT = 'Answer only what you know about the learner.';
const SILENT_ERROR_CONFIG = { skipErrorToast: true };

const createErrorWithCode = (message: string, code: number) =>
  Object.assign(new Error(message), { code });

const createDeferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
};

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOperationProfileOnboardingConfig: jest.fn(),
    updateAdminOperationProfileOnboardingConfig: jest.fn(),
    generateAdminOperationProfileOnboardingAssistantPrompt: jest.fn(),
    createAdminOperationProfileOnboardingPreview: jest.fn(),
  },
}));

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock('../useOperatorGuard', () => ({
  __esModule: true,
  default: () => ({ isReady: true }),
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({
    trackEvent: (...args: unknown[]) => mockTrackEvent(...args),
  }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, string>) =>
      params?.keys ? `${key}:${params.keys}` : key,
    i18n: { language: 'zh-CN', resolvedLanguage: 'zh-CN' },
  }),
}));

jest.mock('@/lib/profileOnboardingSse', () => ({
  streamProfileOnboardingRuntime: jest.fn(() => ({ close: jest.fn() })),
}));

jest.mock(
  '@/components/profile-onboarding/ProfileOnboardingConversation',
  () => ({
    __esModule: true,
    default: ({
      createSession,
      runSession,
      onDraftReady,
    }: {
      createSession: () => Promise<{ session_id: string }>;
      runSession: (params: {
        sessionId: string;
        expectedBlockIndex: number;
        requestId: string;
        userInput?: Record<string, string[]>;
        onMessage: () => void;
        onError: () => void;
      }) => unknown;
      onDraftReady: (draft: string, sessionId: string) => void;
    }) => (
      <button
        type='button'
        onClick={async () => {
          const session = await createSession();
          runSession({
            sessionId: session.session_id,
            expectedBlockIndex: 2,
            requestId: 'preview-run-1',
            userInput: { research_topic: ['AI 教学'] },
            onMessage: () => undefined,
            onError: () => undefined,
          });
          onDraftReady('预览个人介绍', session.session_id);
        }}
      >
        {RUN_MOCKED_PREVIEW_LABEL}
      </button>
    ),
  }),
);

const mockGetConfig = api.getAdminOperationProfileOnboardingConfig as jest.Mock;
const mockUpdateConfig =
  api.updateAdminOperationProfileOnboardingConfig as jest.Mock;
const mockGeneratePrompt =
  api.generateAdminOperationProfileOnboardingAssistantPrompt as jest.Mock;
const mockCreatePreview =
  api.createAdminOperationProfileOnboardingPreview as jest.Mock;

const renderLoadedPage = async () => {
  render(<ProfileOnboardingAdminPage />);
  return screen.findByLabelText('module.profileOnboarding.admin.markdownflow');
};

const getTrackingCalls = (eventName: string) =>
  mockTrackEvent.mock.calls.filter(([name]) => name === eventName);

const getConfigLoadRetryTrackingCalls = () =>
  mockTrackEvent.mock.calls.filter(([name]) =>
    String(name).startsWith('operator_profile_config_load_retry_'),
  );

const getDirtyNavigationTrackingCalls = () =>
  mockTrackEvent.mock.calls.filter(([name]) =>
    String(name).startsWith('operator_profile_dirty_navigation_'),
  );

describe('ProfileOnboardingAdminPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockTrackEvent.mockReset();
    mockGetConfig.mockResolvedValue({
      enabled: true,
      markdownflow: DOCUMENT,
      assistant_prompt: PROMPT,
      config_revision: 2,
      updated_by: 'operator-1',
      updated_at: '2026-06-15T00:00:00Z',
    });
    mockGeneratePrompt.mockResolvedValue({
      assistant_prompt: 'Generated prompt',
    });
    mockUpdateConfig.mockResolvedValue({
      enabled: true,
      markdownflow: DOCUMENT,
      assistant_prompt: PROMPT,
      config_revision: 3,
    });
    mockCreatePreview.mockResolvedValue({ session_id: 'preview-session-1' });
  });

  test('places an explicit regenerate action below the editable document', async () => {
    const editor = await renderLoadedPage();
    const generateButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.admin.regenerateAssistantPrompt',
    });
    const prompt = screen.getByLabelText(
      'module.profileOnboarding.admin.assistantPrompt',
    );

    expect(prompt).toHaveValue(PROMPT);
    expect(prompt).not.toHaveAttribute('readonly');
    expect(getConfigLoadRetryTrackingCalls()).toHaveLength(0);
    expect(editor).toHaveClass(
      'focus-visible:ring-2',
      'focus-visible:ring-primary/40',
      'focus-visible:ring-offset-2',
    );
    expect(prompt).toHaveClass(
      'focus-visible:ring-2',
      'focus-visible:ring-primary/40',
      'focus-visible:ring-offset-2',
    );
    expect(
      editor.compareDocumentPosition(generateButton) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      generateButton.compareDocumentPosition(prompt) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  test('generates a draft without saving and records one accepted attempt and result', async () => {
    mockGetConfig.mockResolvedValue({
      enabled: false,
      markdownflow: DOCUMENT,
      assistant_prompt: '',
      config_revision: 2,
    });
    await renderLoadedPage();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.generateAssistantPrompt',
      }),
    );

    await waitFor(() =>
      expect(mockGeneratePrompt).toHaveBeenCalledWith({
        markdownflow: DOCUMENT,
      }),
    );
    expect(mockUpdateConfig).not.toHaveBeenCalled();
    expect(
      await screen.findByDisplayValue('Generated prompt'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.profileOnboarding.admin.generateSuccess'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.regenerateAssistantPrompt',
      }),
    ).toBeInTheDocument();
    expect(mockTrackEvent).toHaveBeenNthCalledWith(
      1,
      PROFILE_PROMPT_GENERATE_ATTEMPT_EVENT,
      { mode: 'generate' },
    );
    expect(mockTrackEvent).toHaveBeenNthCalledWith(
      2,
      PROFILE_PROMPT_GENERATE_RESULT_EVENT,
      { mode: 'generate', outcome: 'success' },
    );
    expect(mockTrackEvent.mock.calls.flat()).not.toContain(DOCUMENT);
    expect(mockTrackEvent.mock.calls.flat()).not.toContain('Generated prompt');
  });

  test('prevents duplicate generation while leaving both editors writable', async () => {
    const deferred = createDeferred<{ assistant_prompt: string }>();
    mockGeneratePrompt.mockReturnValue(deferred.promise);
    const documentEditor = await renderLoadedPage();
    const promptEditor = screen.getByLabelText(
      'module.profileOnboarding.admin.assistantPrompt',
    );
    const generateButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.admin.regenerateAssistantPrompt',
    });

    fireEvent.click(generateButton);
    fireEvent.click(generateButton);

    expect(mockGeneratePrompt).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.generatingAssistantPrompt',
      }),
    ).toBeDisabled();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    ).toBeDisabled();
    expect(documentEditor).toBeEnabled();
    expect(promptEditor).toBeEnabled();

    await act(async () =>
      deferred.resolve({ assistant_prompt: 'Fresh prompt' }),
    );
    await screen.findByDisplayValue('Fresh prompt');
  });

  test('does not overwrite edits made while generation is in flight', async () => {
    const deferred = createDeferred<{ assistant_prompt: string }>();
    mockGeneratePrompt.mockReturnValue(deferred.promise);
    const documentEditor = await renderLoadedPage();
    const promptEditor = screen.getByLabelText(
      'module.profileOnboarding.admin.assistantPrompt',
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.regenerateAssistantPrompt',
      }),
    );
    fireEvent.change(documentEditor, {
      target: { value: '?[...Newer unsaved question]' },
    });
    fireEvent.change(promptEditor, {
      target: { value: 'Newer manual prompt' },
    });
    await act(async () =>
      deferred.resolve({ assistant_prompt: 'Stale generated prompt' }),
    );

    expect(documentEditor).toHaveValue('?[...Newer unsaved question]');
    expect(promptEditor).toHaveValue('Newer manual prompt');
    expect(
      await screen.findByText(
        'module.profileOnboarding.admin.generationSuperseded',
      ),
    ).toBeInTheDocument();
    expect(mockTrackEvent).toHaveBeenLastCalledWith(
      PROFILE_PROMPT_GENERATE_RESULT_EVENT,
      { mode: 'regenerate', outcome: 'superseded' },
    );
  });

  test('keeps the existing draft on generation failure and analytics stays fail-open', async () => {
    mockGeneratePrompt.mockRejectedValue(new Error('sensitive provider error'));
    mockTrackEvent.mockImplementation(() => {
      throw new Error('tracking unavailable');
    });
    await renderLoadedPage();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.regenerateAssistantPrompt',
      }),
    );

    expect(
      await screen.findByText('module.profileOnboarding.admin.generateFailed'),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText('module.profileOnboarding.admin.assistantPrompt'),
    ).toHaveValue(PROMPT);
    expect(
      screen.queryByText('sensitive provider error'),
    ).not.toBeInTheDocument();
    expect(mockGeneratePrompt).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenLastCalledWith(
      PROFILE_PROMPT_GENERATE_RESULT_EVENT,
      { mode: 'regenerate', outcome: 'failed' },
    );
  });

  test('keeps a successful generation when analytics rejects asynchronously', async () => {
    mockTrackEvent.mockRejectedValue(new Error('tracking rejected'));
    await renderLoadedPage();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.regenerateAssistantPrompt',
      }),
    );

    expect(
      await screen.findByDisplayValue('Generated prompt'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.profileOnboarding.admin.generateSuccess'),
    ).toBeInTheDocument();
    expect(mockTrackEvent).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  test('validates generation before sending a request or analytics event', async () => {
    mockGetConfig.mockResolvedValue({
      enabled: false,
      markdownflow: '',
      assistant_prompt: '',
      config_revision: 2,
    });
    await renderLoadedPage();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.generateAssistantPrompt',
      }),
    );

    expect(
      await screen.findByText(
        'module.profileOnboarding.admin.generateRequiresDocument',
      ),
    ).toBeInTheDocument();
    expect(mockGeneratePrompt).not.toHaveBeenCalled();
    expect(mockTrackEvent).not.toHaveBeenCalled();
  });

  test('marks an existing prompt for review after the document changes and clears it after manual editing', async () => {
    const editor = await renderLoadedPage();
    const prompt = screen.getByLabelText(
      'module.profileOnboarding.admin.assistantPrompt',
    );

    fireEvent.change(editor, { target: { value: '?[...Changed question]' } });
    expect(
      screen.getByText('module.profileOnboarding.admin.documentChanged'),
    ).toBeInTheDocument();
    fireEvent.change(prompt, { target: { value: 'Manually aligned prompt' } });
    expect(
      screen.queryByText('module.profileOnboarding.admin.documentChanged'),
    ).not.toBeInTheDocument();
  });

  test('saves the complete draft and revision, then adopts the returned baseline', async () => {
    mockUpdateConfig.mockResolvedValue({
      enabled: true,
      markdownflow: '?[...Changed question]',
      assistant_prompt: 'Saved manual prompt',
      config_revision: 3,
      updated_by: 'operator-2',
      updated_at: '2026-06-16T00:00:00Z',
    });
    const editor = await renderLoadedPage();
    const prompt = screen.getByLabelText(
      'module.profileOnboarding.admin.assistantPrompt',
    );
    fireEvent.change(editor, { target: { value: '?[...Changed question]' } });
    fireEvent.change(prompt, { target: { value: 'Saved manual prompt' } });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );

    await waitFor(() =>
      expect(mockUpdateConfig).toHaveBeenCalledWith(
        {
          enabled: true,
          markdownflow: '?[...Changed question]',
          assistant_prompt: 'Saved manual prompt',
          config_revision: 2,
        },
        SILENT_ERROR_CONFIG,
      ),
    );
    expect(await screen.findByText('3')).toBeInTheDocument();
    expect(mockToast).toHaveBeenCalledWith({
      title: 'module.profileOnboarding.admin.saveSuccess',
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );
    await waitFor(() => expect(mockUpdateConfig).toHaveBeenCalledTimes(2));
    expect(mockUpdateConfig).toHaveBeenLastCalledWith(
      {
        enabled: true,
        markdownflow: '?[...Changed question]',
        assistant_prompt: 'Saved manual prompt',
        config_revision: 3,
      },
      SILENT_ERROR_CONFIG,
    );
  });

  test('requires both document and assistant prompt when enabled', async () => {
    mockGetConfig.mockResolvedValue({
      enabled: true,
      markdownflow: DOCUMENT,
      assistant_prompt: '',
      config_revision: 2,
    });
    const editor = await renderLoadedPage();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );
    expect(
      await screen.findByText(
        'module.profileOnboarding.admin.assistantPromptRequired',
      ),
    ).toBeInTheDocument();
    expect(mockUpdateConfig).not.toHaveBeenCalled();

    fireEvent.change(editor, { target: { value: '' } });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );
    expect(
      await screen.findByText(
        'module.profileOnboarding.admin.documentRequired',
      ),
    ).toBeInTheDocument();
  });

  test('rejects an orphan prompt but allows a disabled empty configuration', async () => {
    mockGetConfig.mockResolvedValue({
      enabled: false,
      markdownflow: '',
      assistant_prompt: 'Orphan prompt',
      config_revision: 2,
    });
    mockUpdateConfig.mockResolvedValue({
      enabled: false,
      markdownflow: '',
      assistant_prompt: '',
      config_revision: 3,
    });
    await renderLoadedPage();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );
    expect(
      await screen.findByText(
        'module.profileOnboarding.admin.promptRequiresDocument',
      ),
    ).toBeInTheDocument();
    expect(mockUpdateConfig).not.toHaveBeenCalled();

    fireEvent.change(
      screen.getByLabelText('module.profileOnboarding.admin.assistantPrompt'),
      { target: { value: '' } },
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );
    await waitFor(() =>
      expect(mockUpdateConfig).toHaveBeenCalledWith(
        {
          enabled: false,
          markdownflow: '',
          assistant_prompt: '',
          config_revision: 2,
        },
        SILENT_ERROR_CONFIG,
      ),
    );
  });

  test('preserves edits made during save and submits them against the returned revision', async () => {
    const deferred = createDeferred<Record<string, unknown>>();
    mockUpdateConfig.mockReturnValueOnce(deferred.promise);
    await renderLoadedPage();
    const prompt = screen.getByLabelText(
      'module.profileOnboarding.admin.assistantPrompt',
    );
    fireEvent.change(prompt, { target: { value: 'Submitted prompt' } });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );
    fireEvent.change(prompt, { target: { value: 'Newer unsaved prompt' } });

    await act(async () =>
      deferred.resolve({
        enabled: true,
        markdownflow: DOCUMENT,
        assistant_prompt: 'Submitted prompt',
        config_revision: 3,
      }),
    );
    expect(prompt).toHaveValue('Newer unsaved prompt');
    expect(await screen.findByText('3')).toBeInTheDocument();

    mockUpdateConfig.mockResolvedValue({
      enabled: true,
      markdownflow: DOCUMENT,
      assistant_prompt: 'Newer unsaved prompt',
      config_revision: 4,
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );
    await waitFor(() =>
      expect(mockUpdateConfig).toHaveBeenLastCalledWith(
        {
          enabled: true,
          markdownflow: DOCUMENT,
          assistant_prompt: 'Newer unsaved prompt',
          config_revision: 3,
        },
        SILENT_ERROR_CONFIG,
      ),
    );
  });

  test('retains drafts on non-conflict failures without refreshing and reports cache delay separately', async () => {
    mockUpdateConfig.mockRejectedValueOnce(new Error('Publication failed'));
    await renderLoadedPage();
    const prompt = screen.getByLabelText(
      'module.profileOnboarding.admin.assistantPrompt',
    );
    fireEvent.change(prompt, { target: { value: 'Unsaved prompt' } });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );
    expect(await screen.findByText('Publication failed')).toBeInTheDocument();
    expect(prompt).toHaveValue('Unsaved prompt');
    expect(mockGetConfig).toHaveBeenCalledTimes(1);

    mockUpdateConfig.mockResolvedValue({
      enabled: true,
      markdownflow: DOCUMENT,
      assistant_prompt: 'Unsaved prompt',
      config_revision: 3,
      cache_refresh_pending: true,
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );
    await waitFor(() =>
      expect(mockToast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'module.profileOnboarding.admin.saveCacheRefreshPending',
          duration: 8000,
        }),
      ),
    );
  });

  test('refreshes a conflicting saved baseline while preserving edits made during recovery', async () => {
    const refreshedConfig = createDeferred<Record<string, unknown>>();
    mockGetConfig
      .mockResolvedValueOnce({
        enabled: true,
        markdownflow: DOCUMENT,
        assistant_prompt: PROMPT,
        config_revision: 2,
        updated_by: 'operator-1',
        updated_at: '2026-06-15T00:00:00Z',
      })
      .mockReturnValueOnce(refreshedConfig.promise);
    mockUpdateConfig.mockRejectedValueOnce(
      createErrorWithCode('A newer version exists', 4015),
    );
    const editor = await renderLoadedPage();
    const prompt = screen.getByLabelText(
      'module.profileOnboarding.admin.assistantPrompt',
    );
    const localDocument = '?[...Local question]';
    fireEvent.change(editor, { target: { value: localDocument } });
    fireEvent.change(prompt, {
      target: { value: 'Local prompt before refresh' },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );

    await waitFor(() => expect(mockGetConfig).toHaveBeenCalledTimes(2));
    expect(mockGetConfig).toHaveBeenNthCalledWith(2, {}, SILENT_ERROR_CONFIG);
    expect(editor).toBeEnabled();
    expect(prompt).toBeEnabled();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    ).toBeDisabled();
    fireEvent.change(prompt, {
      target: { value: 'Newest local prompt during refresh' },
    });

    await act(async () =>
      refreshedConfig.resolve({
        enabled: false,
        markdownflow: '?[...Remote question]',
        assistant_prompt: 'Remote prompt',
        config_revision: 5,
        updated_by: 'operator-remote',
        updated_at: '2026-06-17T00:00:00Z',
      }),
    );
    expect(
      await screen.findByText(
        'module.profileOnboarding.admin.configConflictRecovered',
      ),
    ).toBeInTheDocument();
    expect(editor).toHaveValue(localDocument);
    expect(prompt).toHaveValue('Newest local prompt during refresh');
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('operator-remote')).toBeInTheDocument();
    expect(mockUpdateConfig).toHaveBeenCalledTimes(1);
    expect(getConfigLoadRetryTrackingCalls()).toHaveLength(0);

    mockUpdateConfig.mockResolvedValueOnce({
      enabled: true,
      markdownflow: localDocument,
      assistant_prompt: 'Newest local prompt during refresh',
      config_revision: 6,
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );
    await waitFor(() =>
      expect(mockUpdateConfig).toHaveBeenLastCalledWith(
        {
          enabled: true,
          markdownflow: localDocument,
          assistant_prompt: 'Newest local prompt during refresh',
          config_revision: 5,
        },
        SILENT_ERROR_CONFIG,
      ),
    );
  });

  test('keeps the stale revision and draft when conflict recovery cannot refresh', async () => {
    mockGetConfig
      .mockResolvedValueOnce({
        enabled: true,
        markdownflow: DOCUMENT,
        assistant_prompt: PROMPT,
        config_revision: 2,
      })
      .mockRejectedValueOnce(new Error('refresh unavailable'));
    mockUpdateConfig.mockRejectedValueOnce(
      createErrorWithCode('A newer version exists', 4015),
    );
    await renderLoadedPage();
    const prompt = screen.getByLabelText(
      'module.profileOnboarding.admin.assistantPrompt',
    );
    fireEvent.change(prompt, { target: { value: 'Preserved local prompt' } });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );

    expect(
      await screen.findByText(
        'module.profileOnboarding.admin.configConflictRefreshFailed',
      ),
    ).toBeInTheDocument();
    expect(prompt).toHaveValue('Preserved local prompt');
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(mockUpdateConfig).toHaveBeenCalledTimes(1);
    expect(mockGetConfig).toHaveBeenCalledTimes(2);
  });

  test('rejects a conflict refresh that does not advance the saved revision', async () => {
    mockGetConfig
      .mockResolvedValueOnce({
        enabled: true,
        markdownflow: DOCUMENT,
        assistant_prompt: PROMPT,
        config_revision: 2,
      })
      .mockResolvedValueOnce({
        enabled: false,
        markdownflow: '?[...Unconfirmed remote question]',
        assistant_prompt: 'Unconfirmed remote prompt',
        config_revision: 2,
      });
    mockUpdateConfig.mockRejectedValueOnce(
      createErrorWithCode('A newer version exists', 4015),
    );
    await renderLoadedPage();
    const prompt = screen.getByLabelText(
      'module.profileOnboarding.admin.assistantPrompt',
    );
    fireEvent.change(prompt, { target: { value: 'Preserved local prompt' } });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );

    expect(
      await screen.findByText(
        'module.profileOnboarding.admin.configConflictRefreshFailed',
      ),
    ).toBeInTheDocument();
    expect(prompt).toHaveValue('Preserved local prompt');
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(
      screen.queryByText('Unconfirmed remote prompt'),
    ).not.toBeInTheDocument();
  });

  test('locks mutations after load failure and tracks one successful retry', async () => {
    mockGetConfig.mockRejectedValueOnce(new Error('network failed'));
    render(<ProfileOnboardingAdminPage />);

    expect(
      await screen.findByText('module.profileOnboarding.admin.loadFailed'),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText('module.profileOnboarding.admin.markdownflow'),
    ).toBeDisabled();
    expect(
      screen.getByLabelText('module.profileOnboarding.admin.assistantPrompt'),
    ).toBeDisabled();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.generateAssistantPrompt',
      }),
    ).toBeDisabled();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    ).toBeDisabled();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.preview',
      }),
    ).toBeDisabled();
    expect(
      screen.getByRole('switch', {
        name: 'module.profileOnboarding.admin.enabled',
      }),
    ).toBeDisabled();
    expect(getConfigLoadRetryTrackingCalls()).toHaveLength(0);

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.reload',
      }),
    );
    expect(await screen.findByDisplayValue(DOCUMENT)).toBeEnabled();
    expect(mockGetConfig).toHaveBeenCalledTimes(2);
    expect(getConfigLoadRetryTrackingCalls()).toEqual([
      [PROFILE_CONFIG_LOAD_RETRY_ATTEMPT_EVENT, {}],
      [PROFILE_CONFIG_LOAD_RETRY_RESULT_EVENT, { outcome: 'success' }],
    ]);
    expect(mockTrackEvent.mock.invocationCallOrder[0]).toBeLessThan(
      mockGetConfig.mock.invocationCallOrder[1],
    );
    expect(mockTrackEvent.mock.invocationCallOrder[1]).toBeGreaterThan(
      mockGetConfig.mock.invocationCallOrder[1],
    );
    const serializedTracking = JSON.stringify(
      getConfigLoadRetryTrackingCalls(),
    );
    for (const prohibitedValue of [
      DOCUMENT,
      PROMPT,
      'network failed',
      'zh-CN',
      '/admin/operations/profile-onboarding',
      'operator-1',
      'config_revision',
      'updated_at',
    ]) {
      expect(serializedTracking).not.toContain(prohibitedValue);
    }
  });

  test('tracks failed reloads and a later deliberate retry separately', async () => {
    mockGetConfig
      .mockRejectedValueOnce(new Error('initial sensitive failure'))
      .mockRejectedValueOnce(new Error('retry sensitive failure'));
    render(<ProfileOnboardingAdminPage />);

    expect(
      await screen.findByText('module.profileOnboarding.admin.loadFailed'),
    ).toBeInTheDocument();
    expect(getConfigLoadRetryTrackingCalls()).toHaveLength(0);

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.reload',
      }),
    );
    await waitFor(() =>
      expect(getConfigLoadRetryTrackingCalls()).toEqual([
        [PROFILE_CONFIG_LOAD_RETRY_ATTEMPT_EVENT, {}],
        [PROFILE_CONFIG_LOAD_RETRY_RESULT_EVENT, { outcome: 'failed' }],
      ]),
    );
    expect(
      screen.getByLabelText('module.profileOnboarding.admin.markdownflow'),
    ).toBeDisabled();
    expect(
      screen.queryByText('retry sensitive failure'),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.reload',
      }),
    );
    expect(await screen.findByDisplayValue(DOCUMENT)).toBeEnabled();
    expect(mockGetConfig).toHaveBeenCalledTimes(3);
    expect(getConfigLoadRetryTrackingCalls()).toEqual([
      [PROFILE_CONFIG_LOAD_RETRY_ATTEMPT_EVENT, {}],
      [PROFILE_CONFIG_LOAD_RETRY_RESULT_EVENT, { outcome: 'failed' }],
      [PROFILE_CONFIG_LOAD_RETRY_ATTEMPT_EVENT, {}],
      [PROFILE_CONFIG_LOAD_RETRY_RESULT_EVENT, { outcome: 'success' }],
    ]);
  });

  test.each([
    {
      analyticsFailure: 'throws synchronously',
      configureTrackingFailure: () => {
        mockTrackEvent.mockImplementation(() => {
          throw new Error('tracking unavailable');
        });
      },
    },
    {
      analyticsFailure: 'rejects asynchronously',
      configureTrackingFailure: () => {
        mockTrackEvent.mockRejectedValue(new Error('tracking rejected'));
      },
    },
  ])(
    'prevents duplicate reloads and stays fail-open when analytics $analyticsFailure',
    async ({ configureTrackingFailure }) => {
      const retry = createDeferred<Record<string, unknown>>();
      mockGetConfig
        .mockRejectedValueOnce(new Error('initial load failed'))
        .mockReturnValueOnce(retry.promise);
      render(<ProfileOnboardingAdminPage />);
      expect(
        await screen.findByText('module.profileOnboarding.admin.loadFailed'),
      ).toBeInTheDocument();
      configureTrackingFailure();
      const reloadButton = screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.reload',
      });

      act(() => {
        reloadButton.click();
        reloadButton.click();
      });

      expect(mockGetConfig).toHaveBeenCalledTimes(2);
      expect(getTrackingCalls(PROFILE_CONFIG_LOAD_RETRY_ATTEMPT_EVENT)).toEqual(
        [[PROFILE_CONFIG_LOAD_RETRY_ATTEMPT_EVENT, {}]],
      );
      expect(
        getTrackingCalls(PROFILE_CONFIG_LOAD_RETRY_RESULT_EVENT),
      ).toHaveLength(0);

      await act(async () =>
        retry.resolve({
          enabled: true,
          markdownflow: DOCUMENT,
          assistant_prompt: PROMPT,
          config_revision: 2,
        }),
      );

      expect(await screen.findByDisplayValue(DOCUMENT)).toBeEnabled();
      expect(mockGetConfig).toHaveBeenCalledTimes(2);
      expect(getConfigLoadRetryTrackingCalls()).toEqual([
        [PROFILE_CONFIG_LOAD_RETRY_ATTEMPT_EVENT, {}],
        [PROFILE_CONFIG_LOAD_RETRY_RESULT_EVENT, { outcome: 'success' }],
      ]);
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    },
  );

  test('warns before browser or same-origin navigation when the draft is dirty', async () => {
    const editor = await renderLoadedPage();
    fireEvent.change(editor, { target: { value: '?[...Unsaved question]' } });

    await waitFor(() => {
      const event = new Event('beforeunload', {
        bubbles: false,
        cancelable: true,
      });
      window.dispatchEvent(event);
      expect(event.defaultPrevented).toBe(true);
    });
    expect(getDirtyNavigationTrackingCalls()).toHaveLength(0);

    const anchor = document.createElement('a');
    anchor.href = '/admin/operations';
    anchor.textContent = 'leave page';
    anchor.addEventListener('click', event => {
      if (!event.defaultPrevented) {
        mockPush('/navigated-by-downstream-link-handler');
      }
    });
    document.body.appendChild(anchor);
    fireEvent.click(anchor);
    expect(
      await screen.findByText(
        'module.profileOnboarding.admin.unsavedDialog.title',
      ),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(getTrackingCalls(PROFILE_DIRTY_NAVIGATION_SHOWN_EVENT)).toEqual([
        [PROFILE_DIRTY_NAVIGATION_SHOWN_EVENT, {}],
      ]),
    );
    expect(mockPush).not.toHaveBeenCalled();

    fireEvent.click(anchor);
    expect(getTrackingCalls(PROFILE_DIRTY_NAVIGATION_SHOWN_EVENT)).toHaveLength(
      1,
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.unsavedDialog.discard',
      }),
    );
    expect(mockPush).toHaveBeenCalledWith('/admin/operations', {
      scroll: false,
    });
    expect(getDirtyNavigationTrackingCalls()).toEqual([
      [PROFILE_DIRTY_NAVIGATION_SHOWN_EVENT, {}],
      [PROFILE_DIRTY_NAVIGATION_DECISION_EVENT, { decision: 'discard' }],
    ]);
    const trackedPayload = JSON.stringify(getDirtyNavigationTrackingCalls());
    expect(trackedPayload).not.toContain('/admin/operations');
    expect(trackedPayload).not.toContain('Unsaved question');
    expect(trackedPayload).not.toContain(PROMPT);
    expect(trackedPayload).not.toContain('config_revision');
    expect(trackedPayload).not.toContain('error');
    anchor.remove();
  });

  test('tracks cancelling the dirty-navigation dialog without navigating', async () => {
    const editor = await renderLoadedPage();
    fireEvent.change(editor, { target: { value: '?[...Keep editing]' } });
    const anchor = document.createElement('a');
    anchor.href = '/admin/operations';
    document.body.appendChild(anchor);
    fireEvent.click(anchor);

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'module.profileOnboarding.admin.unsavedDialog.cancel',
      }),
    );

    await waitFor(() =>
      expect(getDirtyNavigationTrackingCalls()).toEqual([
        [PROFILE_DIRTY_NAVIGATION_SHOWN_EVENT, {}],
        [PROFILE_DIRTY_NAVIGATION_DECISION_EVENT, { decision: 'cancel' }],
      ]),
    );
    expect(mockPush).not.toHaveBeenCalled();
    expect(
      screen.queryByText('module.profileOnboarding.admin.unsavedDialog.title'),
    ).not.toBeInTheDocument();
    anchor.remove();
  });

  test('excludes native and ineligible navigation from dirty-navigation analytics', async () => {
    const editor = await renderLoadedPage();
    fireEvent.change(editor, { target: { value: '?[...Unsaved question]' } });

    const beforeUnload = new Event('beforeunload', {
      bubbles: false,
      cancelable: true,
    });
    window.dispatchEvent(beforeUnload);
    expect(beforeUnload.defaultPrevented).toBe(true);

    const anchors = [
      Object.assign(document.createElement('a'), { href: '#same-page' }),
      Object.assign(document.createElement('a'), {
        href: 'https://example.com/elsewhere',
      }),
      Object.assign(document.createElement('a'), {
        href: '/admin/operations',
        target: '_blank',
      }),
      Object.assign(document.createElement('a'), {
        href: '/admin/download',
        download: 'config.txt',
      }),
    ];
    for (const anchor of anchors) {
      anchor.addEventListener('click', event => event.preventDefault());
      document.body.appendChild(anchor);
      fireEvent.click(anchor);
    }
    const modifiedClickAnchor = document.createElement('a');
    modifiedClickAnchor.href = '/admin/operations';
    modifiedClickAnchor.addEventListener('click', event =>
      event.preventDefault(),
    );
    document.body.appendChild(modifiedClickAnchor);
    fireEvent.click(modifiedClickAnchor, { ctrlKey: true });

    expect(getDirtyNavigationTrackingCalls()).toHaveLength(0);
    expect(
      screen.queryByText('module.profileOnboarding.admin.unsavedDialog.title'),
    ).not.toBeInTheDocument();
    for (const anchor of [...anchors, modifiedClickAnchor]) {
      anchor.remove();
    }
  });

  test.each([
    [
      'throws synchronously',
      () => {
        throw new Error('tracking unavailable');
      },
    ],
    ['rejects asynchronously', () => Promise.reject(new Error('blocked'))],
  ])(
    'keeps save-and-leave fail-open when tracking %s',
    async (_label, trackingImplementation) => {
      mockTrackEvent.mockImplementation(trackingImplementation);
      const changedDocument = '?[...Save despite analytics failure]';
      mockUpdateConfig.mockResolvedValue({
        enabled: true,
        markdownflow: changedDocument,
        assistant_prompt: PROMPT,
        config_revision: 3,
      });
      const editor = await renderLoadedPage();
      fireEvent.change(editor, { target: { value: changedDocument } });
      const anchor = document.createElement('a');
      anchor.href = '/admin/operations';
      document.body.appendChild(anchor);
      fireEvent.click(anchor);
      fireEvent.click(
        await screen.findByRole('button', {
          name: 'module.profileOnboarding.admin.unsavedDialog.save',
        }),
      );

      await waitFor(() =>
        expect(mockPush).toHaveBeenCalledWith('/admin/operations', {
          scroll: false,
        }),
      );
      expect(mockUpdateConfig).toHaveBeenCalledTimes(1);
      anchor.remove();
    },
  );

  test('freezes the navigation decision while save-and-proceed is in flight', async () => {
    const deferred = createDeferred<Record<string, unknown>>();
    mockUpdateConfig.mockReturnValue(deferred.promise);
    const submittedDocument = '?[...Unsaved question to persist]';
    const editor = await renderLoadedPage();
    fireEvent.change(editor, { target: { value: submittedDocument } });

    const originalAnchor = document.createElement('a');
    originalAnchor.href = '/admin/operations';
    originalAnchor.textContent = 'leave after save';
    document.body.appendChild(originalAnchor);
    fireEvent.click(originalAnchor);
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'module.profileOnboarding.admin.unsavedDialog.save',
      }),
    );

    await waitFor(() =>
      expect(mockUpdateConfig).toHaveBeenCalledWith(
        {
          enabled: true,
          markdownflow: submittedDocument,
          assistant_prompt: PROMPT,
          config_revision: 2,
        },
        SILENT_ERROR_CONFIG,
      ),
    );
    expect(getTrackingCalls(PROFILE_DIRTY_NAVIGATION_DECISION_EVENT)).toEqual([
      [PROFILE_DIRTY_NAVIGATION_DECISION_EVENT, { decision: 'save_and_leave' }],
    ]);
    const cancelButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.admin.unsavedDialog.cancel',
    });
    const discardButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.admin.unsavedDialog.discard',
    });
    const saveAndLeaveButton = screen.getByRole('button', {
      name: 'module.profileOnboarding.admin.unsavedDialog.save',
    });
    expect(cancelButton).toBeDisabled();
    expect(discardButton).toBeDisabled();
    expect(saveAndLeaveButton).toBeDisabled();

    fireEvent.click(cancelButton);
    fireEvent.click(discardButton);
    fireEvent.keyDown(screen.getByRole('alertdialog'), { key: 'Escape' });

    const competingAnchor = document.createElement('a');
    competingAnchor.href = '/admin/another-destination';
    competingAnchor.textContent = 'change destination';
    competingAnchor.addEventListener('click', event => {
      if (!event.defaultPrevented) {
        mockPush('/navigated-by-competing-link-handler');
      }
    });
    document.body.appendChild(competingAnchor);
    fireEvent.click(competingAnchor);

    expect(mockPush).not.toHaveBeenCalled();
    expect(
      getTrackingCalls(PROFILE_DIRTY_NAVIGATION_DECISION_EVENT),
    ).toHaveLength(1);
    expect(
      getTrackingCalls(PROFILE_DIRTY_NAVIGATION_SAVE_RESULT_EVENT),
    ).toHaveLength(0);
    expect(getTrackingCalls(PROFILE_DIRTY_NAVIGATION_SHOWN_EVENT)).toHaveLength(
      1,
    );
    expect(
      screen.getByText('module.profileOnboarding.admin.unsavedDialog.title'),
    ).toBeInTheDocument();

    await act(async () =>
      deferred.resolve({
        enabled: true,
        markdownflow: submittedDocument,
        assistant_prompt: PROMPT,
        config_revision: 3,
      }),
    );
    await waitFor(() =>
      expect(mockPush).toHaveBeenCalledWith('/admin/operations', {
        scroll: false,
      }),
    );
    expect(mockPush).toHaveBeenCalledTimes(1);
    expect(getDirtyNavigationTrackingCalls()).toEqual([
      [PROFILE_DIRTY_NAVIGATION_SHOWN_EVENT, {}],
      [PROFILE_DIRTY_NAVIGATION_DECISION_EVENT, { decision: 'save_and_leave' }],
      [PROFILE_DIRTY_NAVIGATION_SAVE_RESULT_EVENT, { outcome: 'success' }],
    ]);
    const decisionCallIndex = mockTrackEvent.mock.calls.findIndex(
      ([name]) => name === PROFILE_DIRTY_NAVIGATION_DECISION_EVENT,
    );
    const resultCallIndex = mockTrackEvent.mock.calls.findIndex(
      ([name]) => name === PROFILE_DIRTY_NAVIGATION_SAVE_RESULT_EVENT,
    );
    expect(
      mockTrackEvent.mock.invocationCallOrder[decisionCallIndex],
    ).toBeLessThan(mockUpdateConfig.mock.invocationCallOrder[0]);
    expect(mockUpdateConfig.mock.invocationCallOrder[0]).toBeLessThan(
      mockTrackEvent.mock.invocationCallOrder[resultCallIndex],
    );
    expect(
      mockTrackEvent.mock.invocationCallOrder[resultCallIndex],
    ).toBeLessThan(mockPush.mock.invocationCallOrder[0]);
    originalAnchor.remove();
    competingAnchor.remove();
  });

  test('shows save-and-leave validation errors inside the dialog', async () => {
    mockGetConfig.mockResolvedValue({
      enabled: true,
      markdownflow: DOCUMENT,
      assistant_prompt: '',
      config_revision: 2,
    });
    const editor = await renderLoadedPage();
    fireEvent.change(editor, { target: { value: '?[...Changed question]' } });
    const anchor = document.createElement('a');
    anchor.href = '/admin/operations';
    document.body.appendChild(anchor);
    fireEvent.click(anchor);

    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(
      within(dialog).getByRole('button', {
        name: 'module.profileOnboarding.admin.unsavedDialog.save',
      }),
    );

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      'module.profileOnboarding.admin.assistantPromptRequired',
    );
    expect(mockUpdateConfig).not.toHaveBeenCalled();
    expect(mockPush).not.toHaveBeenCalled();
    expect(editor).toHaveValue('?[...Changed question]');
    expect(getDirtyNavigationTrackingCalls()).toEqual([
      [PROFILE_DIRTY_NAVIGATION_SHOWN_EVENT, {}],
      [PROFILE_DIRTY_NAVIGATION_DECISION_EVENT, { decision: 'save_and_leave' }],
      [PROFILE_DIRTY_NAVIGATION_SAVE_RESULT_EVENT, { outcome: 'failed' }],
    ]);
    anchor.remove();
  });

  test('shows save-and-leave API failures and tracks a deliberate retry', async () => {
    mockUpdateConfig.mockRejectedValueOnce(new Error('Publication failed'));
    const editor = await renderLoadedPage();
    fireEvent.change(editor, { target: { value: '?[...Changed question]' } });
    const anchor = document.createElement('a');
    anchor.href = '/admin/operations';
    document.body.appendChild(anchor);
    fireEvent.click(anchor);

    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(
      within(dialog).getByRole('button', {
        name: 'module.profileOnboarding.admin.unsavedDialog.save',
      }),
    );

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      'Publication failed',
    );
    expect(mockPush).not.toHaveBeenCalled();
    expect(editor).toHaveValue('?[...Changed question]');
    expect(
      within(dialog).getByRole('button', {
        name: 'module.profileOnboarding.admin.unsavedDialog.discard',
      }),
    ).toBeEnabled();
    expect(getDirtyNavigationTrackingCalls()).toEqual([
      [PROFILE_DIRTY_NAVIGATION_SHOWN_EVENT, {}],
      [PROFILE_DIRTY_NAVIGATION_DECISION_EVENT, { decision: 'save_and_leave' }],
      [PROFILE_DIRTY_NAVIGATION_SAVE_RESULT_EVENT, { outcome: 'failed' }],
    ]);

    const changedDocument = '?[...Changed question]';
    mockUpdateConfig.mockResolvedValueOnce({
      enabled: true,
      markdownflow: changedDocument,
      assistant_prompt: PROMPT,
      config_revision: 3,
    });
    fireEvent.click(
      within(dialog).getByRole('button', {
        name: 'module.profileOnboarding.admin.unsavedDialog.save',
      }),
    );
    await waitFor(() =>
      expect(mockPush).toHaveBeenCalledWith('/admin/operations', {
        scroll: false,
      }),
    );
    expect(getTrackingCalls(PROFILE_DIRTY_NAVIGATION_DECISION_EVENT)).toEqual([
      [PROFILE_DIRTY_NAVIGATION_DECISION_EVENT, { decision: 'save_and_leave' }],
      [PROFILE_DIRTY_NAVIGATION_DECISION_EVENT, { decision: 'save_and_leave' }],
    ]);
    expect(
      getTrackingCalls(PROFILE_DIRTY_NAVIGATION_SAVE_RESULT_EVENT),
    ).toEqual([
      [PROFILE_DIRTY_NAVIGATION_SAVE_RESULT_EVENT, { outcome: 'failed' }],
      [PROFILE_DIRTY_NAVIGATION_SAVE_RESULT_EVENT, { outcome: 'success' }],
    ]);
    anchor.remove();
  });

  test('keeps save-and-leave open after a conflict and uses the refreshed revision on retry', async () => {
    const localDocument = '?[...Local dialog question]';
    mockGetConfig
      .mockResolvedValueOnce({
        enabled: true,
        markdownflow: DOCUMENT,
        assistant_prompt: PROMPT,
        config_revision: 2,
      })
      .mockResolvedValueOnce({
        enabled: true,
        markdownflow: '?[...Remote dialog question]',
        assistant_prompt: 'Remote dialog prompt',
        config_revision: 5,
        updated_by: 'operator-remote',
      });
    mockUpdateConfig.mockRejectedValueOnce(
      createErrorWithCode('A newer version exists', 4015),
    );
    const editor = await renderLoadedPage();
    fireEvent.change(editor, { target: { value: localDocument } });
    const anchor = document.createElement('a');
    anchor.href = '/admin/operations';
    document.body.appendChild(anchor);
    fireEvent.click(anchor);

    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(
      within(dialog).getByRole('button', {
        name: 'module.profileOnboarding.admin.unsavedDialog.save',
      }),
    );

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      'module.profileOnboarding.admin.configConflictRecovered',
    );
    expect(editor).toHaveValue(localDocument);
    expect(mockPush).not.toHaveBeenCalled();
    expect(mockUpdateConfig).toHaveBeenCalledTimes(1);

    mockUpdateConfig.mockResolvedValueOnce({
      enabled: true,
      markdownflow: localDocument,
      assistant_prompt: PROMPT,
      config_revision: 6,
    });
    fireEvent.click(
      within(dialog).getByRole('button', {
        name: 'module.profileOnboarding.admin.unsavedDialog.save',
      }),
    );

    await waitFor(() =>
      expect(mockUpdateConfig).toHaveBeenLastCalledWith(
        {
          enabled: true,
          markdownflow: localDocument,
          assistant_prompt: PROMPT,
          config_revision: 5,
        },
        SILENT_ERROR_CONFIG,
      ),
    );
    await waitFor(() =>
      expect(mockPush).toHaveBeenCalledWith('/admin/operations', {
        scroll: false,
      }),
    );
    expect(
      getTrackingCalls(PROFILE_DIRTY_NAVIGATION_SAVE_RESULT_EVENT),
    ).toEqual([
      [PROFILE_DIRTY_NAVIGATION_SAVE_RESULT_EVENT, { outcome: 'failed' }],
      [PROFILE_DIRTY_NAVIGATION_SAVE_RESULT_EVENT, { outcome: 'success' }],
    ]);
    anchor.remove();
  });

  test('shows a modal status and keeps the destination when newer edits supersede a saved draft', async () => {
    const deferred = createDeferred<Record<string, unknown>>();
    mockUpdateConfig.mockReturnValue(deferred.promise);
    const submittedDocument = '?[...Submitted question]';
    const newerDocument = '?[...Newer question during save]';
    const editor = await renderLoadedPage();
    fireEvent.change(editor, { target: { value: submittedDocument } });
    const anchor = document.createElement('a');
    anchor.href = '/admin/operations';
    document.body.appendChild(anchor);
    fireEvent.click(anchor);

    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(
      within(dialog).getByRole('button', {
        name: 'module.profileOnboarding.admin.unsavedDialog.save',
      }),
    );
    await waitFor(() => expect(mockUpdateConfig).toHaveBeenCalledTimes(1));
    fireEvent.change(editor, { target: { value: newerDocument } });
    await act(async () =>
      deferred.resolve({
        enabled: true,
        markdownflow: submittedDocument,
        assistant_prompt: PROMPT,
        config_revision: 3,
      }),
    );

    expect(await within(dialog).findByRole('status')).toHaveTextContent(
      'module.profileOnboarding.admin.unsavedDialog.newerEditsAfterSave',
    );
    expect(mockPush).not.toHaveBeenCalled();
    expect(editor).toHaveValue(newerDocument);
    expect(
      within(dialog).getByRole('button', {
        name: 'module.profileOnboarding.admin.unsavedDialog.save',
      }),
    ).toBeEnabled();
    expect(getDirtyNavigationTrackingCalls()).toEqual([
      [PROFILE_DIRTY_NAVIGATION_SHOWN_EVENT, {}],
      [PROFILE_DIRTY_NAVIGATION_DECISION_EVENT, { decision: 'save_and_leave' }],
      [PROFILE_DIRTY_NAVIGATION_SAVE_RESULT_EVENT, { outcome: 'superseded' }],
    ]);
    anchor.remove();
  });

  test('creates an isolated preview from the current unsaved document', async () => {
    const editor = await renderLoadedPage();
    fireEvent.change(editor, {
      target: { value: '?[%{{unsaved_topic}}...未保存的问题？]' },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.preview',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: RUN_MOCKED_PREVIEW_LABEL }),
    );

    await waitFor(() =>
      expect(mockCreatePreview).toHaveBeenCalledWith({
        markdownflow: '?[%{{unsaved_topic}}...未保存的问题？]',
        language: 'zh-CN',
      }),
    );
    expect(streamProfileOnboardingRuntime).toHaveBeenCalledWith(
      expect.objectContaining({
        path: '/api/shifu/admin/operations/profile-onboarding/preview/preview-session-1/run',
        payload: {
          expected_block_index: 2,
          request_id: 'preview-run-1',
          user_input: { research_topic: ['AI 教学'] },
        },
      }),
    );
    expect(await screen.findByDisplayValue('预览个人介绍')).toBeInTheDocument();
    expect(mockUpdateConfig).not.toHaveBeenCalled();
    expect(mockGeneratePrompt).not.toHaveBeenCalled();
  });
});
