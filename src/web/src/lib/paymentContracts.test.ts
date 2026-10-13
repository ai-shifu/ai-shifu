import {
  hasPaymentMethod,
  defaultPaymentSelection,
  resolvePaymentAction,
  resolvePaymentOption,
  canOpenPaymentQr,
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
    {
      type: 'sdk_confirm',
      sdk: 'fixture-sdk',
      client_secret: 'fixture-secret',
    },
    { type: 'qr', url: 'payapp://signed-payment' },
    { type: 'qr', url: 'opaque signed payment token' },
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
      for (const type of ['redirect'] as const) {
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
  test.each([
    'payapp://signed-payment',
    'opaque signed payment token',
    'javascript:alert(1)',
    'data:text/html,test',
    'file:///tmp/pay',
  ])('renders opaque QR data without granting navigation: %s', url => {
    expect(
      resolvePaymentAction({
        payment_contract_version: 1,
        payment_action: { type: 'qr', url },
      }),
    ).toEqual({ type: 'qr', url });
    expect(
      resolvePaymentAction({ channel: 'fixture_qr', qr_url: url }),
    ).toEqual({ type: 'qr', url });
    expect(canOpenPaymentQr(url)).toBe(false);
  });
  test.each(['', '   '])('rejects empty QR data and SDK names: %s', value => {
    expect(
      resolvePaymentAction({
        payment_contract_version: 1,
        payment_action: { type: 'qr', url: value },
      }),
    ).toBeNull();
    expect(
      resolvePaymentAction({
        payment_contract_version: 1,
        payment_action: {
          type: 'sdk_confirm',
          sdk: value,
          client_secret: 'secret',
        },
      }),
    ).toBeNull();
  });
  test.each([
    'https://pay.example/qr',
    'http://pay.example/qr',
    'weixin://pay',
    'alipay://pay',
    'alipays://pay',
  ])('preserves existing mobile launch support: %s', url =>
    expect(canOpenPaymentQr(url)).toBe(true),
  );
});

test('default selection keeps gateway identity for shared routes and respects JSAPI preference', () => {
  const options: PaymentOption[] = [
    {
      ...option,
      id: 'first:shared',
      provider: 'first',
      channel: 'shared',
      method: 'wechat',
      action: 'qr',
      scene: 'qr',
    },
    {
      ...option,
      id: 'second:shared',
      provider: 'second',
      channel: 'shared',
      method: 'wechat',
      action: 'jsapi',
      scene: 'wechat',
      prefer_in_wechat: true,
    },
  ];
  expect(defaultPaymentSelection(options, false)).toBe('first:shared');
  expect(defaultPaymentSelection(options, true)).toBe('second:shared');
  expect(defaultPaymentSelection([], true)).toBeUndefined();
});
import {
  resolvePaymentPresentation,
  resolveRequestedPaymentProvider,
} from './paymentContracts';

describe('shared payment presentation and compatibility', () => {
  it('preserves a hosted action independently of the gateway name', () => {
    const presentation = resolvePaymentPresentation({
      action: {
        type: 'redirect',
        url: 'https://checkout.example.test/pay',
        session_id: 'attempt-one',
      },
      provider: 'another-hosted',
    });
    expect(presentation.hostedCheckoutUrl).toBe(
      'https://checkout.example.test/pay',
    );
    expect(presentation.checkoutSessionId).toBe('attempt-one');
    expect(presentation.stripeClientSecret).toBeUndefined();
  });

  it('never falls back to a legacy success action after explicit rejection', () => {
    expect(
      resolvePaymentPresentation({
        action: null,
        legacyPayload: {
          checkout_session_url: 'https://old.example.test/pay',
          client_secret: 'old-secret',
        },
        provider: 'stripe',
      }).action,
    ).toBeNull();
  });

  it('keeps SDK confirmation and old API recovery in the compatibility boundary', () => {
    const result = resolvePaymentPresentation({
      provider: 'stripe',
      legacyPayload: { client_secret: 'test-secret' },
    });
    expect(result.confirmationMode).toBe('payment_intent');
    expect(result.stripeClientSecret).toBe('test-secret');
    expect(result.hostedCheckoutUrl).toBe('');
    expect(
      resolveRequestedPaymentProvider([], 'stripe', ['stripe']),
    ).toBeUndefined();
    expect(
      resolveRequestedPaymentProvider(undefined, 'wx_pub', ['wechatpay']),
    ).toBe('wechatpay');
  });
});
