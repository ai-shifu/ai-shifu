jest.unmock('i18next');

import { render, screen } from '@testing-library/react';
import i18next from 'i18next';
import ICU from 'i18next-icu';
import { I18nextProvider } from 'react-i18next';
import { SWRConfig } from 'swr';

import api from '@/api';
import { AdminBillingReportsPanel } from './AdminBillingReportsPanel';
import arBilling from '../../../../i18n/ar-SA/modules/billing.json';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: { getAdminBillingFocusTeachers: jest.fn() },
}));

describe('Arabic billing activity counts', () => {
  const i18n = i18next.createInstance().use(new ICU());

  beforeAll(async () => {
    await i18n.init({
      lng: 'ar-SA',
      fallbackLng: false,
      resources: {
        'ar-SA': { translation: { module: { billing: arBilling } } },
      },
    });
  });

  test.each([
    [1, 'نشط لمدة يوم واحد خلال آخر 7 أيام'],
    [2, 'نشط لمدة يومين خلال آخر 7 أيام'],
    [3, 'نشط لمدة ٣ أيام خلال آخر 7 أيام'],
    [7, 'نشط لمدة ٧ أيام خلال آخر 7 أيام'],
  ])(
    'renders %i active days with ICU number formatting',
    async (days, hint) => {
      (api.getAdminBillingFocusTeachers as jest.Mock).mockResolvedValue({
        total: 1,
        items: [
          {
            creator_bid: 'teacher-1',
            creator_nickname: 'Teacher',
            active_days_7d: days,
            latest_usage_at: '2026-04-07T00:00:00Z',
            attention_reasons: [],
          },
        ],
      });

      render(
        <I18nextProvider i18n={i18n}>
          <SWRConfig value={{ provider: () => new Map() }}>
            <AdminBillingReportsPanel />
          </SWRConfig>
        </I18nextProvider>,
      );

      expect(await screen.findByText(hint)).toBeInTheDocument();
      expect(screen.queryByText(/ليس رقمًا/)).not.toBeInTheDocument();
    },
  );
});
