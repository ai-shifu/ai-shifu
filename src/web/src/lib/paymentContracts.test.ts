import {
  hasPaymentMethod,
  resolvePaymentAction,
  resolvePaymentOption,
} from './paymentContracts';
import type { PaymentAction, PaymentOption } from '@/types/payment';

const option: PaymentOption = {
  id: 'fixture-hosted:checkout',
  provider: 'fixture-hosted',
  channel: 'checkout',
  method: 'hosted',
  scene: 'hosted',
  action: 'redirect',
  billing_mode: 'provider_managed',
  label_key: 'module.billing.catalog.labels.providerStripe',
  poll_provider: false,
  requires_open_id: false,
};

describe('shared payment contracts', () => {
  test.each<PaymentAction>([
    { type: 'qr', url: 'https://fixture.test/qr' },
    {
      type: 'redirect',
      url: 'https://fixture.test/checkout',
      session_id: 'fixture-session',
    },
    {
      type: 'jsapi',
      parameters: {
        appId: 'fixture-app',
        timeStamp: '1',
        nonceStr: 'nonce',
        package: 'prepay_id=fixture',
        signType: 'RSA',
        paySign: 'signed',
      },
    },
    { type: 'sdk_confirm', sdk: 'stripe', client_secret: 'fixture-secret' },
    { type: 'none' },
  ])(
    'executes the declared $type action independently of gateway identity',
    action => {
      expect(
        resolvePaymentAction({
          provider: 'fixture-pay',
          payment_contract_version: 1,
          payment_action: action,
          qr_url: 'obsolete',
        }),
      ).toEqual(action);
    },
  );

  test('does not reinterpret unknown or invalid new actions using legacy fields', () => {
    for (const version of [1, 2]) {
      expect(
        resolvePaymentAction({
          payment_contract_version: version,
          payment_action: { type: 'unknown' } as unknown as PaymentAction,
          qr_url: 'https://fixture.test/obsolete',
        }),
      ).toBeNull();
      expect(
        resolvePaymentAction({
          payment_contract_version: version,
          payment_action: null,
          redirect_url: 'https://fixture.test/obsolete',
        }),
      ).toBeNull();
    }
    expect(
      resolvePaymentAction({
        payment_contract_version: 1,
        payment_action: { type: 'redirect', url: '' },
      }),
    ).toBeNull();
  });

  test('supports old backend QR, hosted, JSAPI and embedded-confirmation payloads', () => {
    expect(
      resolvePaymentAction({
        provider: 'pingxx',
        channel: 'alipay_qr',
        qr_url: 'https://fixture.test/qr',
      })?.type,
    ).toBe('qr');
    expect(
      resolvePaymentAction({
        provider: 'stripe',
        redirect_url: 'https://fixture.test/checkout',
      })?.type,
    ).toBe('redirect');
    expect(
      resolvePaymentAction({
        provider: 'stripe',
        payment_payload: { client_secret: 'fixture-secret' },
      }),
    ).toEqual({
      type: 'sdk_confirm',
      sdk: 'stripe',
      client_secret: 'fixture-secret',
    });
    expect(
      resolvePaymentAction({
        provider: 'wechatpay',
        payment_payload: {
          mode: 'jsapi',
          jsapi_params: { appId: 'fixture-app' },
        },
      })?.type,
    ).toBe('jsapi');
  });

  test('selects an added hosted integration without a built-in gateway whitelist', () => {
    expect(resolvePaymentOption([option], option.id)).toBe(option);
    expect(resolvePaymentOption([option], 'stripe')).toBe(option);
    expect(hasPaymentMethod([option], 'hosted')).toBe(true);
    expect(resolvePaymentOption([], 'stripe')).toBeUndefined();
    expect(hasPaymentMethod([], 'hosted')).toBe(false);
  });
});

describe('payment URL execution boundaries', () => {
  test.each([undefined, 1])(
    'rejects executable or malformed URLs for contract %s',
    version => {
      for (const type of ['redirect', 'qr'] as const) {
        for (const url of [
          'javascript:alert(1)',
          'data:text/html,test',
          'file:///tmp/pay',
          '//pay.example/test',
          'invalid',
        ]) {
          const result =
            version === undefined
              ? { provider: 'stripe', redirect_url: url }
              : {
                  payment_contract_version: version,
                  payment_action: { type, url },
                };
          expect(resolvePaymentAction(result)).toBeNull();
        }
      }
    },
  );
  test.each([
    'weixin://wxpay/bizpayurl?pr=test',
    'alipay://pay',
    'alipays://pay',
    'https://pay.example/qr',
    'http://pay.example/qr',
  ])('preserves native and web QR data %s', url => {
    expect(
      resolvePaymentAction({
        payment_contract_version: 1,
        payment_action: { type: 'qr', url },
      }),
    ).toEqual({ type: 'qr', url });
    expect(
      resolvePaymentAction({
        provider: 'wechatpay',
        channel: 'wx_pub_qr',
        qr_url: url,
      }),
    ).toEqual({ type: 'qr', url });
    if (!url.startsWith('http')) {
      expect(
        resolvePaymentAction({
          payment_contract_version: 1,
          payment_action: { type: 'redirect', url },
        }),
      ).toBeNull();
    }
  });
});
