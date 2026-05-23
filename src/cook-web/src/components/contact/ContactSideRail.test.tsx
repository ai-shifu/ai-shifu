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

  test('renders a right-aligned square trigger with a hover label panel', () => {
    render(<ContactSideRail label='Nous contacter' />);

    const contactLink = screen.getByRole('link', {
      name: 'Nous contacter',
    });
    const rail = screen.getByTestId('contact-side-rail');
    const trigger = screen.getByTestId('contact-side-rail-trigger');
    const labelPanel = screen.getByTestId('contact-side-rail-label');
    const label = screen.getByText('Nous contacter');

    expect(contactLink).toHaveAttribute('title', 'Nous contacter');
    expect(contactLink).toHaveClass('h-10');
    expect(contactLink).toHaveClass('w-10');
    expect(contactLink).toHaveClass('bg-primary');
    expect(rail).toHaveClass('right-0');
    expect(trigger).toHaveClass('h-10');
    expect(trigger).toHaveClass('w-10');
    expect(labelPanel).toHaveClass('whitespace-nowrap');
    expect(labelPanel).toHaveClass('group-hover:max-w-56');
    expect(label).toHaveClass('whitespace-nowrap');
    expect(label).not.toHaveClass('break-all');
  });

  test('does not render when the contact url is empty', () => {
    mockEnvState.contactUsUrl = '';

    render(<ContactSideRail />);

    expect(
      screen.queryByRole('link', { name: CONTACT_RAIL_I18N_KEY }),
    ).not.toBeInTheDocument();
  });
});
