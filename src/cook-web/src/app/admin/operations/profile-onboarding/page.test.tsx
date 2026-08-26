import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import api from '@/api';
import { streamProfileOnboardingRuntime } from '@/lib/profileOnboardingSse';
import ProfileOnboardingAdminPage from './page';

const mockToast = jest.fn();
const RUN_MOCKED_PREVIEW_LABEL = 'run mocked preview';

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOperationProfileOnboardingConfig: jest.fn(),
    updateAdminOperationProfileOnboardingConfig: jest.fn(),
    createAdminOperationProfileOnboardingPreview: jest.fn(),
  },
}));

jest.mock('../useOperatorGuard', () => ({
  __esModule: true,
  default: () => ({
    isReady: true,
  }),
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({
    toast: mockToast,
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
          onDraftReady('预览画像', session.session_id);
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
const mockCreatePreview =
  api.createAdminOperationProfileOnboardingPreview as jest.Mock;

describe('ProfileOnboardingAdminPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetConfig.mockResolvedValue({
      enabled: true,
      markdownflow: '?[%{{research_topic}}...最近在关注什么？]',
      assistant_prompt: 'Answer only what you know about the learner.',
      config_revision: 2,
      updated_by: 'operator-1',
      updated_at: '2026-06-15T00:00:00+00:00',
    });
    mockCreatePreview.mockResolvedValue({ session_id: 'preview-session-1' });
  });

  test('shows an editable prompt but omits it when only the document changes', async () => {
    mockUpdateConfig.mockResolvedValue({
      enabled: true,
      markdownflow: '?[%{{arbitrary_runtime_variable}}...你的目标？]',
      assistant_prompt: 'Describe the learner goals you know.',
      config_revision: 3,
    });

    render(<ProfileOnboardingAdminPage />);

    const editor = await screen.findByDisplayValue(
      '?[%{{research_topic}}...最近在关注什么？]',
    );
    const assistantPrompt = screen.getByLabelText(
      'module.profileOnboarding.admin.assistantPrompt',
    );
    expect(assistantPrompt).not.toHaveAttribute('readonly');
    expect(assistantPrompt).toHaveValue(
      'Answer only what you know about the learner.',
    );
    fireEvent.change(editor, {
      target: {
        value: '?[%{{arbitrary_runtime_variable}}...你的目标？]',
      },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );

    await waitFor(() => {
      expect(mockUpdateConfig).toHaveBeenCalledWith({
        enabled: true,
        markdownflow: '?[%{{arbitrary_runtime_variable}}...你的目标？]',
      });
    });
    await waitFor(() => {
      expect(assistantPrompt).toHaveValue(
        'Describe the learner goals you know.',
      );
    });
    expect(mockToast).toHaveBeenCalledWith({
      title: 'module.profileOnboarding.admin.saveSuccess',
    });
  });

  test('saves an intentionally edited prompt with document changes and adopts the returned saved result', async () => {
    mockUpdateConfig.mockResolvedValue({
      enabled: true,
      markdownflow: '?[...Changed question]',
      assistant_prompt: 'Saved manual prompt',
      config_revision: 3,
    });
    render(<ProfileOnboardingAdminPage />);
    const editor = await screen.findByLabelText(
      'module.profileOnboarding.admin.markdownflow',
    );
    const prompt = screen.getByLabelText(
      'module.profileOnboarding.admin.assistantPrompt',
    );
    fireEvent.change(editor, { target: { value: '?[...Changed question]' } });
    fireEvent.change(prompt, { target: { value: '  Saved manual prompt  ' } });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );
    await waitFor(() =>
      expect(mockUpdateConfig).toHaveBeenCalledWith({
        enabled: true,
        markdownflow: '?[...Changed question]',
        assistant_prompt: '  Saved manual prompt  ',
      }),
    );
    await waitFor(() => expect(prompt).toHaveValue('Saved manual prompt'));
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );
    await waitFor(() =>
      expect(mockUpdateConfig).toHaveBeenLastCalledWith({
        enabled: true,
        markdownflow: '?[...Changed question]',
      }),
    );
  });

  test('sends an explicit blank prompt to regenerate it and then treats the result as the saved baseline', async () => {
    mockUpdateConfig.mockResolvedValue({
      enabled: true,
      markdownflow: '?[%{{research_topic}}...最近在关注什么？]',
      assistant_prompt: 'Regenerated public prompt',
      config_revision: 3,
    });
    render(<ProfileOnboardingAdminPage />);
    const prompt = await screen.findByLabelText(
      'module.profileOnboarding.admin.assistantPrompt',
    );
    fireEvent.change(prompt, { target: { value: '' } });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );
    await waitFor(() =>
      expect(mockUpdateConfig).toHaveBeenCalledWith({
        enabled: true,
        markdownflow: '?[%{{research_topic}}...最近在关注什么？]',
        assistant_prompt: '',
      }),
    );
    await waitFor(() =>
      expect(prompt).toHaveValue('Regenerated public prompt'),
    );
    fireEvent.click(
      screen.getByRole('switch', {
        name: 'module.profileOnboarding.admin.enabled',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );
    await waitFor(() =>
      expect(mockUpdateConfig).toHaveBeenLastCalledWith({
        enabled: false,
        markdownflow: '?[%{{research_topic}}...最近在关注什么？]',
      }),
    );
  });

  test('retains manual prompt edits and its prior saved baseline when saving fails', async () => {
    mockUpdateConfig.mockRejectedValueOnce(new Error('Publication failed'));
    render(<ProfileOnboardingAdminPage />);
    const prompt = await screen.findByLabelText(
      'module.profileOnboarding.admin.assistantPrompt',
    );
    fireEvent.change(prompt, { target: { value: 'Unsaved manual prompt' } });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Publication failed',
    );
    expect(prompt).toHaveValue('Unsaved manual prompt');
    mockUpdateConfig.mockResolvedValue({
      enabled: true,
      markdownflow: '?[%{{research_topic}}...最近在关注什么？]',
      assistant_prompt: 'Unsaved manual prompt',
      config_revision: 3,
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );
    await waitFor(() => expect(mockUpdateConfig).toHaveBeenCalledTimes(2));
    expect(mockUpdateConfig.mock.calls[1][0]).toEqual(
      mockUpdateConfig.mock.calls[0][0],
    );
    expect(mockUpdateConfig.mock.calls[1][0].assistant_prompt).toBe(
      'Unsaved manual prompt',
    );
    await waitFor(() =>
      expect(screen.queryByRole('alert')).not.toBeInTheDocument(),
    );
  });

  test('preserves prompt edits typed during save and sends them relative to the returned saved baseline', async () => {
    let resolveSave!: (response: Record<string, unknown>) => void;
    mockUpdateConfig.mockReturnValueOnce(
      new Promise(resolve => {
        resolveSave = resolve;
      }),
    );
    render(<ProfileOnboardingAdminPage />);
    const prompt = await screen.findByLabelText(
      'module.profileOnboarding.admin.assistantPrompt',
    );
    fireEvent.change(prompt, { target: { value: 'Submitted manual prompt' } });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );
    fireEvent.change(prompt, {
      target: { value: 'Newer manual edit during save' },
    });
    await act(async () =>
      resolveSave({
        enabled: true,
        markdownflow: '?[%{{research_topic}}...最近在关注什么？]',
        assistant_prompt: 'Submitted manual prompt',
        config_revision: 3,
      }),
    );
    expect(prompt).toHaveValue('Newer manual edit during save');
    expect(screen.getByText('3')).toBeInTheDocument();
    mockUpdateConfig.mockResolvedValue({
      enabled: true,
      markdownflow: '?[%{{research_topic}}...最近在关注什么？]',
      assistant_prompt: 'Newer manual edit during save',
      config_revision: 4,
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );
    await waitFor(() =>
      expect(mockUpdateConfig).toHaveBeenLastCalledWith({
        enabled: true,
        markdownflow: '?[%{{research_topic}}...最近在关注什么？]',
        assistant_prompt: 'Newer manual edit during save',
      }),
    );
    await screen.findByText('4');
  });

  test('omits the unchanged prompt when clearing a disabled document and reflects the cleared saved result', async () => {
    mockUpdateConfig.mockResolvedValue({
      enabled: false,
      markdownflow: '',
      assistant_prompt: '',
      config_revision: 3,
    });
    render(<ProfileOnboardingAdminPage />);
    const editor = await screen.findByLabelText(
      'module.profileOnboarding.admin.markdownflow',
    );
    fireEvent.click(
      screen.getByRole('switch', {
        name: 'module.profileOnboarding.admin.enabled',
      }),
    );
    fireEvent.change(editor, { target: { value: '' } });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );
    await waitFor(() =>
      expect(mockUpdateConfig).toHaveBeenCalledWith({
        enabled: false,
        markdownflow: '',
      }),
    );
    await waitFor(() =>
      expect(
        screen.getByLabelText('module.profileOnboarding.admin.assistantPrompt'),
      ).toHaveValue(''),
    );
  });

  test('does not silently discard an edited prompt when its document is cleared', async () => {
    mockUpdateConfig.mockResolvedValue({
      enabled: false,
      markdownflow: '',
      assistant_prompt: '',
      config_revision: 3,
    });
    render(<ProfileOnboardingAdminPage />);
    const editor = await screen.findByLabelText(
      'module.profileOnboarding.admin.markdownflow',
    );
    const prompt = screen.getByLabelText(
      'module.profileOnboarding.admin.assistantPrompt',
    );
    fireEvent.click(
      screen.getByRole('switch', {
        name: 'module.profileOnboarding.admin.enabled',
      }),
    );
    fireEvent.change(editor, { target: { value: '' } });
    fireEvent.change(prompt, { target: { value: 'Keep this edited prompt' } });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'module.profileOnboarding.admin.promptRequiresDocument',
    );
    expect(mockUpdateConfig).not.toHaveBeenCalled();
    expect(prompt).toHaveValue('Keep this edited prompt');
    expect(editor).toHaveValue('');
    fireEvent.change(prompt, { target: { value: '' } });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );
    await waitFor(() =>
      expect(mockUpdateConfig).toHaveBeenCalledWith({
        enabled: false,
        markdownflow: '',
        assistant_prompt: '',
      }),
    );
  });

  test('keeps the edited document and last published prompt after generation fails', async () => {
    mockUpdateConfig.mockRejectedValue(new Error('Prompt generation failed'));
    render(<ProfileOnboardingAdminPage />);
    const editor = await screen.findByLabelText(
      'module.profileOnboarding.admin.markdownflow',
    );
    fireEvent.change(editor, {
      target: { value: '?[...An unsaved question]' },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Prompt generation failed',
    );
    expect(editor).toHaveValue('?[...An unsaved question]');
    expect(
      screen.getByLabelText('module.profileOnboarding.admin.assistantPrompt'),
    ).toHaveValue('Answer only what you know about the learner.');
    expect(mockToast).not.toHaveBeenCalled();
    expect(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    ).toBeEnabled();
  });

  test('reports a durable save with delayed cache refresh as a warning', async () => {
    mockUpdateConfig.mockResolvedValue({
      enabled: true,
      markdownflow: '?[%{{research_topic}}...最近在关注什么？]',
      assistant_prompt: 'The newly saved public prompt.',
      config_revision: 3,
      cache_refresh_pending: true,
    });
    render(<ProfileOnboardingAdminPage />);
    await screen.findByLabelText('module.profileOnboarding.admin.markdownflow');
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );

    expect(await screen.findByText('3')).toBeInTheDocument();
    expect(
      screen.getByLabelText('module.profileOnboarding.admin.assistantPrompt'),
    ).toHaveValue('The newly saved public prompt.');
    expect(mockToast).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'module.profileOnboarding.admin.saveCacheRefreshPending',
        duration: 8000,
      }),
    );
    expect(mockToast).not.toHaveBeenCalledWith({
      title: 'module.profileOnboarding.admin.saveSuccess',
    });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  test('preserves edits made while the public prompt is being generated', async () => {
    let resolveSave!: (response: Record<string, unknown>) => void;
    mockUpdateConfig.mockReturnValue(
      new Promise(resolve => {
        resolveSave = resolve;
      }),
    );
    render(<ProfileOnboardingAdminPage />);
    const editor = await screen.findByLabelText(
      'module.profileOnboarding.admin.markdownflow',
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );
    fireEvent.change(editor, {
      target: { value: '?[...Another question typed while saving]' },
    });
    await act(async () => {
      resolveSave({
        enabled: true,
        markdownflow: '?[%{{research_topic}}...最近在关注什么？]',
        assistant_prompt: 'Published prompt for the submitted document.',
        config_revision: 3,
      });
    });

    expect(editor).toHaveValue('?[...Another question typed while saving]');
    expect(
      screen.getByLabelText('module.profileOnboarding.admin.assistantPrompt'),
    ).toHaveValue('Published prompt for the submitted document.');
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  test('preserves an intentionally empty MarkdownFlow while disabled', async () => {
    mockGetConfig.mockResolvedValue({
      enabled: false,
      markdownflow: '',
      config_revision: 2,
    });
    mockUpdateConfig.mockResolvedValue({
      enabled: false,
      markdownflow: '',
      config_revision: 3,
    });

    render(<ProfileOnboardingAdminPage />);

    const flowEditor = await screen.findByLabelText(
      'module.profileOnboarding.admin.markdownflow',
    );
    expect(flowEditor).toHaveValue('');
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );

    await waitFor(() => {
      expect(mockUpdateConfig).toHaveBeenCalledWith({
        enabled: false,
        markdownflow: '',
      });
    });
  });

  test('shows localized starter values for a virgin configuration', async () => {
    mockGetConfig.mockResolvedValue({
      enabled: false,
      markdownflow: '',
      config_revision: 0,
      updated_by: '',
      updated_at: '',
    });

    render(<ProfileOnboardingAdminPage />);

    expect(
      await screen.findByLabelText(
        'module.profileOnboarding.admin.markdownflow',
      ),
    ).toHaveValue('module.profileOnboarding.admin.defaultMarkdownflow');
  });

  test('ignores retired version and allowlist fields', async () => {
    mockGetConfig.mockResolvedValue({
      enabled: false,
      markdownflow: '',
      allowed_variable_keys: ['sys_user_background'],
      version: 7,
    });

    render(<ProfileOnboardingAdminPage />);

    await screen.findByLabelText('module.profileOnboarding.admin.markdownflow');
    expect(screen.getAllByText('-')).not.toHaveLength(0);
    expect(screen.queryByText('sys_user_background')).not.toBeInTheDocument();
  });

  test('does not use a retired version alias returned after save', async () => {
    mockUpdateConfig.mockResolvedValue({
      enabled: true,
      markdownflow: '?[%{{research_topic}}...最近在关注什么？]',
      version: 9,
    });

    render(<ProfileOnboardingAdminPage />);
    await screen.findByDisplayValue(
      '?[%{{research_topic}}...最近在关注什么？]',
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );

    expect(await screen.findByText('2')).toBeInTheDocument();
  });

  test('requires a document only when collection is enabled', async () => {
    mockGetConfig.mockResolvedValue({
      enabled: true,
      markdownflow: '',
      config_revision: 2,
    });

    render(<ProfileOnboardingAdminPage />);
    await screen.findByLabelText('module.profileOnboarding.admin.markdownflow');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );

    expect(mockUpdateConfig).not.toHaveBeenCalled();
    expect(
      screen.getByText('module.profileOnboarding.admin.documentRequired'),
    ).toBeInTheDocument();
  });

  test('creates an isolated server preview from unsaved configuration', async () => {
    render(<ProfileOnboardingAdminPage />);
    const flowEditor = await screen.findByDisplayValue(
      '?[%{{research_topic}}...最近在关注什么？]',
    );
    fireEvent.change(flowEditor, {
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

    await waitFor(() => {
      expect(mockCreatePreview).toHaveBeenCalledWith({
        markdownflow: '?[%{{unsaved_topic}}...未保存的问题？]',
        language: 'zh-CN',
      });
    });
    expect(streamProfileOnboardingRuntime).toHaveBeenCalledWith(
      expect.objectContaining({
        path: '/api/shifu/admin/operations/profile-onboarding/preview/preview-session-1/run',
        payload: {
          expected_block_index: 2,
          request_id: 'preview-run-1',
          user_input: { research_topic: ['AI 教学'] },
        },
        language: 'zh-CN',
      }),
    );
    expect(await screen.findByDisplayValue('预览画像')).toBeInTheDocument();
    expect(
      screen.getByText('module.profileOnboarding.admin.previewProfileNotice'),
    ).toBeInTheDocument();
    expect(mockUpdateConfig).not.toHaveBeenCalled();
  });
});
