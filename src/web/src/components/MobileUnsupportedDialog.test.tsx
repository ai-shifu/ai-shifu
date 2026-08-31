import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import MobileUnsupportedDialog from './MobileUnsupportedDialog';

const mockUseUiLayoutStore = jest.fn();

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock('@/c-store/useUiLayoutStore', () => ({
  __esModule: true,
  useUiLayoutStore: (selector: (state: { inMobile: boolean }) => boolean) =>
    mockUseUiLayoutStore(selector),
}));

describe('MobileUnsupportedDialog', () => {
  beforeEach(() => {
    mockUseUiLayoutStore.mockReset();
  });

  test('renders nothing on desktop', () => {
    mockUseUiLayoutStore.mockImplementation(selector =>
      selector({ inMobile: false }),
    );

    render(<MobileUnsupportedDialog />);

    expect(
      screen.queryByText('common.core.mobileUnsupportedTitle'),
    ).not.toBeInTheDocument();
  });

  test('shows the dialog on mobile and closes after confirmation', () => {
    mockUseUiLayoutStore.mockImplementation(selector =>
      selector({ inMobile: true }),
    );

    render(<MobileUnsupportedDialog />);

    expect(
      screen.getByText('common.core.mobileUnsupportedTitle'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('common.core.mobileUnsupportedDescription'),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByText('common.core.ok'));

    expect(
      screen.queryByText('common.core.mobileUnsupportedTitle'),
    ).not.toBeInTheDocument();
  });
});
