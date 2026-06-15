import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import ProfileOnboardingAdminPage from './page';

const mockToast = jest.fn();

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOperationProfileOnboardingConfig: jest.fn(),
    updateAdminOperationProfileOnboardingConfig: jest.fn(),
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
  }),
}));

const mockGetConfig = api.getAdminOperationProfileOnboardingConfig as jest.Mock;
const mockUpdateConfig =
  api.updateAdminOperationProfileOnboardingConfig as jest.Mock;

describe('ProfileOnboardingAdminPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetConfig.mockResolvedValue({
      enabled: true,
      markdownflow: '?[%{{sys_user_nickname}}...怎么称呼你？]',
      allowed_variable_keys: [
        'sys_user_nickname',
        'sys_user_style',
        'sys_user_background',
      ],
      version: 2,
      updated_by: 'operator-1',
      updated_at: '2026-06-15T00:00:00+00:00',
    });
  });

  test('loads and saves profile onboarding configuration', async () => {
    mockUpdateConfig.mockResolvedValue({
      enabled: true,
      markdownflow: '?[%{{sys_user_style}} 简洁 | 详细]',
    });

    render(<ProfileOnboardingAdminPage />);

    const editor = await screen.findByDisplayValue(
      '?[%{{sys_user_nickname}}...怎么称呼你？]',
    );
    fireEvent.change(editor, {
      target: { value: '?[%{{sys_user_style}} 简洁 | 详细]' },
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );

    await waitFor(() => {
      expect(mockUpdateConfig).toHaveBeenCalledWith({
        enabled: true,
        markdownflow: '?[%{{sys_user_style}} 简洁 | 详细]',
      });
    });
    expect(mockToast).toHaveBeenCalledWith({
      title: 'module.profileOnboarding.admin.saveSuccess',
    });
  });

  test('blocks non-whitelisted variables before saving', async () => {
    render(<ProfileOnboardingAdminPage />);

    const editor = await screen.findByDisplayValue(
      '?[%{{sys_user_nickname}}...怎么称呼你？]',
    );
    fireEvent.change(editor, {
      target: { value: '?[%{{sys_user_language}} 中文 | English]' },
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.admin.save',
      }),
    );

    expect(mockUpdateConfig).not.toHaveBeenCalled();
    expect(
      screen.getByText(
        'module.profileOnboarding.admin.invalidVariables:sys_user_language',
      ),
    ).toBeInTheDocument();
  });
});
