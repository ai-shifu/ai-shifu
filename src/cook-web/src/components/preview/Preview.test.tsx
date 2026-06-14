import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import { useBillingOverview } from '@/hooks/useBillingData';
import PreviewSettingsModal, { buildClassroomModeCourseUrl } from './Preview';

const mockSaveMdflow = jest.fn();
const mockTrackEvent = jest.fn();
const mockUseBillingOverview = useBillingOverview as jest.Mock;
let mockCurrentShifu: { bid: string; readonly: boolean } | null = {
  bid: 'shifu-1',
  readonly: false,
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
    currentShifu: mockCurrentShifu,
    actions: {
      saveMdflow: mockSaveMdflow,
    },
  }),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({
    trackEvent: mockTrackEvent,
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
    mockTrackEvent.mockReset();
    (api.previewShifu as jest.Mock).mockReset();
    mockUseBillingOverview.mockReset();
    mockCurrentShifu = {
      bid: 'shifu-1',
      readonly: false,
    };
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
    const classroomLink = screen.getByRole('link', {
      name: /module.preview.classroomMode/,
    });
    expect(previewButton).toBeDisabled();
    expect(classroomLink).toHaveAttribute('href', '/c/shifu-1?mode=classroom');

    fireEvent.click(previewButton);
    fireEvent.click(classroomLink);

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
      screen.getByRole('link', {
        name: /module.preview.classroomMode/,
      }),
    ).toHaveAttribute('href', '/c/shifu-1?mode=classroom');
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

  it('links classroom mode to the course classroom URL', () => {
    mockUseBillingOverview.mockReturnValue({
      data: {
        debug_allowed: true,
      },
    });
    const openSpy = jest.spyOn(window, 'open').mockImplementation(() => null);

    render(<PreviewSettingsModal />);

    const classroomLink = screen.getByRole('link', {
      name: /module.preview.classroomMode/,
    });

    expect(classroomLink).toHaveAttribute('href', '/c/shifu-1?mode=classroom');
    expect(classroomLink).toHaveAttribute('target', '_blank');
    expect(classroomLink).toHaveAttribute('rel', 'noopener noreferrer');

    fireEvent.click(classroomLink);

    expect(mockSaveMdflow).not.toHaveBeenCalled();
    expect(api.previewShifu).not.toHaveBeenCalled();
    expect(openSpy).not.toHaveBeenCalled();
    expect(mockTrackEvent).toHaveBeenCalledWith('creator_shifu_preview_click', {
      shifu_bid: 'shifu-1',
      open_mode: 'classroom',
    });

    openSpy.mockRestore();
  });

  it('hides classroom mode until a course id is available', () => {
    mockCurrentShifu = null;
    mockUseBillingOverview.mockReturnValue({
      data: {
        debug_allowed: true,
      },
    });

    render(<PreviewSettingsModal />);

    expect(
      screen.queryByRole('link', {
        name: /module.preview.classroomMode/,
      }),
    ).not.toBeInTheDocument();
  });

  it('builds classroom course URLs without preview mode', () => {
    expect(buildClassroomModeCourseUrl('course-1')).toBe(
      '/c/course-1?mode=classroom',
    );
    expect(buildClassroomModeCourseUrl(' course 1 ')).toBe(
      '/c/course%201?mode=classroom',
    );
    expect(buildClassroomModeCourseUrl('')).toBe('');
  });
});
