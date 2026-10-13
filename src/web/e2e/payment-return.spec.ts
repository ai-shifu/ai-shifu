import { expect, test } from '@playwright/test';

// These browser tests exercise the shipped pages with isolated HTTP responses.
// They never authorize or create a transaction at an external payment gateway.
for (const mobile of [false, true]) {
  test.describe(
    mobile ? 'mobile payment return' : 'desktop payment return',
    () => {
      test.use({
        viewport: mobile
          ? { width: 390, height: 844 }
          : { width: 1280, height: 800 },
      });

      for (const legacyStripe of [false, true]) {
        const prefix = legacyStripe ? '/payment/stripe' : '/payment';
        const provider = legacyStripe ? 'stripe' : 'fixture-hosted';

        test(`${provider} learner return confirms once using its original sync route`, async ({
          page,
        }) => {
          const syncRequests: string[] = [];
          await page.route('**/api/**', async route => {
            const path = new URL(route.request().url()).pathname;
            if (path === '/api/i18n') {
              await route.continue();
              return;
            }
            let data: object = {};
            if (path === '/api/order/payment-detail') {
              data = {
                payment_channel: provider,
                order_bid: 'browser-order',
                course_id: 'browser-course',
                status: 0,
              };
            } else if (path.endsWith('/sync')) {
              syncRequests.push(path);
              data = {
                payment_channel: provider,
                order_bid: 'browser-order',
                course_id: 'browser-course',
                status: 1,
              };
            }
            await route.fulfill({ json: { code: 0, data } });
          });
          await page.goto(
            `${prefix}/result?order_id=browser-order${legacyStripe ? '&session_id=cs_browser' : ''}`,
          );
          await expect(
            page.getByRole('heading', { name: 'Payment confirmed' }),
          ).toBeVisible();
          expect(syncRequests).toEqual([
            legacyStripe ? '/api/order/stripe/sync' : '/api/order/payment/sync',
          ]);
          await page.waitForTimeout(250);
          expect(syncRequests).toHaveLength(1);
        });

        for (const status of ['paid', 'pending', 'refunded']) {
          test(`${provider} billing return preserves ${status} without false success`, async ({
            page,
          }) => {
            const syncBodies: object[] = [];
            await page.route('**/api/**', async route => {
              const path = new URL(route.request().url()).pathname;
              if (path === '/api/i18n') {
                await route.continue();
                return;
              }
              if (path === '/api/billing/orders/browser-billing/sync')
                syncBodies.push(route.request().postDataJSON());
              await route.fulfill({
                json: {
                  code: 0,
                  data: path.endsWith('/sync') ? { status } : {},
                },
              });
            });
            await page.goto(
              `${prefix}/billing-result?bill_order_bid=browser-billing${legacyStripe ? '&session_id=cs_browser' : ''}`,
            );
            const heading =
              status === 'paid'
                ? 'Billing updated'
                : status === 'pending'
                  ? 'Waiting for billing confirmation'
                  : 'Billing sync failed';
            await expect(
              page.getByRole('heading', { name: heading }),
            ).toBeVisible();
            expect(syncBodies).toEqual([
              legacyStripe ? { session_id: 'cs_browser' } : {},
            ]);
            if (status !== 'paid')
              await expect(
                page.getByRole('heading', { name: 'Billing updated' }),
              ).toHaveCount(0);
          });
        }
      }
    },
  );
}
