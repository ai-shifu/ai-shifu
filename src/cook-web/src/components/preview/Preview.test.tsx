import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import { useBillingOverview } from '@/hooks/useBillingData';
import PreviewSettingsModal, {
  appendClassroomModeToPreviewUrl,
} from './Preview';

const mockSaveMdflow = jest.fn();
const mockUseBillingOverview = useBillingOverview as jest.Mock;

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    previewShifu: jest.fn(),
  },
}));

jest.mock('@/hooks/useBillingData', () => ({
  useBillingOverview: jest.fn(),
}));

jest.mock('@/c-store', () => ({
  __esModule: true,
  useEnvStore: (selector: (state: { billingEnabled: string }) => unknown) =>
    selector({ billingEnabled: 'true' }),
}));

jest.mock('@/store', () => ({
  useShifu: () => ({
    currentShifu: {
      bid: 'shifu-1',
      readonly: false,
    },
    actions: {
      saveMdflow: mockSaveMdflow,
    },
  }),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({
    trackEvent: jest.fn(),
  }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('PreviewSettingsModal', () => {
  beforeEach(() => {
    mockSaveMdflow.mockReset();
    (api.previewShifu as jest.Mock).mockReset();
    mockUseBillingOverview.mockReset();
  });

  it('disables preview when billing softlimit blocks debug', () => {
    mockUseBillingOverview.mockReturnValue({
      data: {
        debug_allowed: false,
      },
    });

    render(<PreviewSettingsModal />);

    const previewButton = screen.getByRole('button', {
      name: /module.preview.previewAll/,
    });
    const classroomButton = screen.getByRole('button', {
      name: /module.preview.classroomMode/,
    });
    expect(previewButton).toBeDisabled();
    expect(classroomButton).toBeDisabled();

    fireEvent.click(previewButton);
    fireEvent.click(classroomButton);

    expect(mockSaveMdflow).not.toHaveBeenCalled();
    expect(api.previewShifu).not.toHaveBeenCalled();
  });

  it('disables preview while billing overview is loading', () => {
    mockUseBillingOverview.mockReturnValue({
      data: undefined,
    });

    render(<PreviewSettingsModal />);

    expect(
      screen.getByRole('button', {
        name: /module.preview.previewAll/,
      }),
    ).toBeDisabled();
    expect(
      screen.getByRole('button', {
        name: /module.preview.classroomMode/,
      }),
    ).toBeDisabled();
  });

  it('starts preview when debug is allowed', async () => {
    mockUseBillingOverview.mockReturnValue({
      data: {
        debug_allowed: true,
      },
    });
    (api.previewShifu as jest.Mock).mockResolvedValue(
      'https://example.com/preview',
    );
    const openSpy = jest.spyOn(window, 'open').mockImplementation(() => null);

    render(<PreviewSettingsModal />);

    const previewButton = screen.getByRole('button', {
      name: /module.preview.previewAll/,
    });
    expect(previewButton).toBeEnabled();

    fireEvent.click(previewButton);

    await waitFor(() => {
      expect(mockSaveMdflow).toHaveBeenCalled();
      expect(api.previewShifu).toHaveBeenCalled();
      expect(openSpy).toHaveBeenCalledWith(
        'https://example.com/preview',
        '_blank',
        'noopener,noreferrer',
      );
    });

    openSpy.mockRestore();
  });

  it('starts classroom mode from the existing preview URL', async () => {
    mockUseBillingOverview.mockReturnValue({
      data: {
        debug_allowed: true,
      },
    });
    (api.previewShifu as jest.Mock).mockResolvedValue(
      'https://example.com/preview?listen=true',
    );
    const openSpy = jest.spyOn(window, 'open').mockImplementation(() => null);

    render(<PreviewSettingsModal />);

    fireEvent.click(
      screen.getByRole('button', {
        name: /module.preview.classroomMode/,
      }),
    );

    await waitFor(() => {
      expect(mockSaveMdflow).toHaveBeenCalled();
      expect(openSpy).toHaveBeenCalledWith(
        'https://example.com/preview?preview=true&mode=classroom',
        '_blank',
        'noopener,noreferrer',
      );
    });

    openSpy.mockRestore();
  });

  it('builds classroom preview URLs without keeping listen mode', () => {
    expect(
      appendClassroomModeToPreviewUrl('https://example.com/c/1?listen=true'),
    ).toBe('https://example.com/c/1?preview=true&mode=classroom');
    expect(appendClassroomModeToPreviewUrl('/c/1?listen=true#slide-2')).toBe(
      '/c/1?preview=true&mode=classroom#slide-2',
    );
  });
});
