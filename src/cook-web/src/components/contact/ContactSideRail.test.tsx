import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import {
  ContactSideRail,
  CONTACT_RAIL_CLICK_EVENT,
  CONTACT_RAIL_I18N_KEY,
} from './ContactSideRail';

const mockTrackEvent = jest.fn();
const mockEnvState = {
  contactUsUrl: 'https://ai-shifu.cn/contact.html',
};

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock('next/navigation', () => ({
  usePathname: () => '/admin',
}));

jest.mock('@/c-store', () => ({
  __esModule: true,
  useEnvStore: (
    selector: ((state: typeof mockEnvState) => unknown) | undefined,
  ) => selector?.(mockEnvState) ?? mockEnvState.contactUsUrl,
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({
    trackEvent: mockTrackEvent,
  }),
}));

describe('ContactSideRail', () => {
  beforeEach(() => {
    mockTrackEvent.mockReset();
    mockEnvState.contactUsUrl = 'https://ai-shifu.cn/contact.html';
  });

  test('tracks click when the contact url is configured', () => {
    render(<ContactSideRail />);

    const contactLink = screen.getByRole('link', {
      name: CONTACT_RAIL_I18N_KEY,
    });

    fireEvent.click(contactLink);

    expect(mockTrackEvent).toHaveBeenCalledWith(CONTACT_RAIL_CLICK_EVENT, {
      page_path: '/admin',
      target_url: 'https://ai-shifu.cn/contact.html',
    });
  });

  test('does not render when the contact url is empty', () => {
    mockEnvState.contactUsUrl = '';

    render(<ContactSideRail />);

    expect(
      screen.queryByRole('link', { name: CONTACT_RAIL_I18N_KEY }),
    ).not.toBeInTheDocument();
  });
});
