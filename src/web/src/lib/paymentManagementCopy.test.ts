import fs from 'fs';
import path from 'path';
import i18next from 'i18next';
jest.unmock('i18next');
const locales = [
  'zh-CN',
  'en-US',
  'fr-FR',
  'de-DE',
  'es-ES',
  'ar-SA',
  'th-TH',
  'ur-PK',
];
const directory = path.resolve(__dirname, '../../../i18n');
const read = (locale: string, name: string) =>
  JSON.parse(
    fs.readFileSync(
      path.join(directory, locale, 'modules', `${name}.json`),
      'utf8',
    ),
  );
test.each(locales)(
  'price instructions and promotion actions remain provider-neutral in %s',
  locale => {
    const prices = read(locale, 'billing').admin.providerPrices;
    for (const text of [
      prices.dialog.description,
      prices.fields.productId,
      prices.fields.priceId,
      ...Object.values(prices.issueMessages),
    ]) {
      expect(text).not.toContain('Stripe');
    }
    expect(prices.dialog.description).toContain('{{provider}}');
    const promotions = read(locale, 'operations-promotion');
    for (const key of [
      'publishProviderDiscounts',
      'retireProviderDiscounts',
      'retryProviderDiscounts',
    ])
      expect(promotions.actions[key]).not.toContain('Stripe');
    expect(
      promotions.messages.packageCampaignProviderSyncRequired,
    ).not.toContain('Stripe');
    expect(promotions.packageCampaign.providerDiscount).not.toContain('Stripe');
  },
);
test('price copy interpolates the actual provider and retains the Stripe display', async () => {
  const i18n = i18next.createInstance();
  await i18n.init({
    lng: 'en-US',
    resources: { 'en-US': { translation: read('en-US', 'billing') } },
  });
  expect(
    i18n.t('admin.providerPrices.fields.priceId', { provider: 'Catalog Pay' }),
  ).toBe('Catalog Pay price ID');
  expect(
    i18n.t('admin.providerPrices.fields.priceId', { provider: 'Stripe' }),
  ).toBe('Stripe price ID');
});
