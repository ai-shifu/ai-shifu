import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import { useBillingOverview } from '@/hooks/useBillingData';
import PreviewSettingsModal from './Preview';

const mockSaveMdflow = jest.fn();
const mockUseBillingOverview = useBillingOverview as jest.Mock;
const mockCurrentNode = {
  bid: 'lesson-1',
  depth: 1,
};

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
    currentNode: mockCurrentNode,
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
    mockCurrentNode.depth = 1;
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
    expect(previewButton).toBeDisabled();

    fireEvent.click(previewButton);

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
  });

  it('starts preview when debug is allowed', async () => {
    mockUseBillingOverview.mockReturnValue({
      data: {
        debug_allowed: true,
      },
    });
    (api.previewShifu as jest.Mock).mockResolvedValue(
      'https://example.com/c/shifu-1?preview=true',
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
        'https://example.com/c/shifu-1?preview=true&lessonid=lesson-1',
        '_blank',
        'noopener,noreferrer',
      );
    });

    openSpy.mockRestore();
  });

  it('removes a stale lessonid when previewing from a root node', async () => {
    mockCurrentNode.depth = 0;
    mockUseBillingOverview.mockReturnValue({
      data: {
        debug_allowed: true,
      },
    });
    (api.previewShifu as jest.Mock).mockResolvedValue(
      'https://example.com/c/shifu-1?preview=true&lessonid=stale-lesson',
    );
    const openSpy = jest.spyOn(window, 'open').mockImplementation(() => null);

    render(<PreviewSettingsModal />);
    fireEvent.click(
      screen.getByRole('button', {
        name: /module.preview.previewAll/,
      }),
    );

    await waitFor(() => {
      expect(openSpy).toHaveBeenCalledWith(
        'https://example.com/c/shifu-1?preview=true',
        '_blank',
        'noopener,noreferrer',
      );
    });

    openSpy.mockRestore();
  });
});
