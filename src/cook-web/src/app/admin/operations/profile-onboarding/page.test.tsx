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
      document_prompt: '只调研与学习有关的信息',
      config_revision: 2,
      updated_by: 'operator-1',
      updated_at: '2026-06-15T00:00:00+00:00',
    });
    mockCreatePreview.mockResolvedValue({ session_id: 'preview-session-1' });
  });

  test('loads and saves the full MarkdownFlow configuration without client regex parsing', async () => {
    mockUpdateConfig.mockResolvedValue({
      enabled: true,
      markdownflow: '?[%{{arbitrary_runtime_variable}}...你的目标？]',
      document_prompt: '根据回答自然追问',
      config_revision: 3,
    });

    render(<ProfileOnboardingAdminPage />);

    const flowEditor = await screen.findByDisplayValue(
      '?[%{{research_topic}}...最近在关注什么？]',
    );
    fireEvent.change(flowEditor, {
      target: {
        value: '?[%{{arbitrary_runtime_variable}}...你的目标？]',
      },
    });
    fireEvent.change(screen.getByDisplayValue('只调研与学习有关的信息'), {
      target: { value: '根据回答自然追问' },
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
        document_prompt: '根据回答自然追问',
      });
    });
    expect(mockToast).toHaveBeenCalledWith({
      title: 'module.profileOnboarding.admin.saveSuccess',
    });
  });

  test('preserves an intentionally empty document prompt', async () => {
    mockGetConfig.mockResolvedValue({
      enabled: false,
      markdownflow: '?[%{{research_topic}}...最近在关注什么？]',
      document_prompt: '',
      config_revision: 2,
    });
    mockUpdateConfig.mockResolvedValue({
      enabled: false,
      markdownflow: '?[%{{research_topic}}...最近在关注什么？]',
      document_prompt: '',
      config_revision: 3,
    });

    render(<ProfileOnboardingAdminPage />);

    expect(
      await screen.findByLabelText(
        'module.profileOnboarding.admin.documentPrompt',
      ),
    ).toHaveValue('');
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );

    await waitFor(() => {
      expect(mockUpdateConfig).toHaveBeenCalledWith({
        enabled: false,
        markdownflow: '?[%{{research_topic}}...最近在关注什么？]',
        document_prompt: '',
      });
    });
  });

  test('creates an isolated server-side runtime preview from the unsaved document', async () => {
    render(<ProfileOnboardingAdminPage />);
    await screen.findByDisplayValue(
      '?[%{{research_topic}}...最近在关注什么？]',
    );

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
        markdownflow: '?[%{{research_topic}}...最近在关注什么？]',
        document_prompt: '只调研与学习有关的信息',
        language: 'zh-CN',
      });
    });
    await waitFor(() => {
      expect(screen.getByDisplayValue('预览画像')).toBeInTheDocument();
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
    expect(
      screen.getByText('module.profileOnboarding.admin.previewProfileNotice'),
    ).toBeInTheDocument();
  });
});
