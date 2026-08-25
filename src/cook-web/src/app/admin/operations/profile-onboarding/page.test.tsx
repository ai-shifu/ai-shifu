import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
      config_revision: 2,
      updated_by: 'operator-1',
      updated_at: '2026-06-15T00:00:00+00:00',
    });
    mockCreatePreview.mockResolvedValue({ session_id: 'preview-session-1' });
  });

  test('saves arbitrary official MarkdownFlow variables without a separate prompt', async () => {
    mockUpdateConfig.mockResolvedValue({
      enabled: true,
      markdownflow: '?[%{{arbitrary_runtime_variable}}...你的目标？]',
      config_revision: 3,
    });

    render(<ProfileOnboardingAdminPage />);

    const editor = await screen.findByDisplayValue(
      '?[%{{research_topic}}...最近在关注什么？]',
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
    expect(screen.getAllByRole('textbox')).toHaveLength(1);
    expect(mockToast).toHaveBeenCalledWith({
      title: 'module.profileOnboarding.admin.saveSuccess',
    });
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
