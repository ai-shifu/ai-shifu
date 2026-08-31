import { isWechatCodeFlowEnabled, isWechatJsapiAvailable } from './wechatJsapi';

describe('isWechatCodeFlowEnabled', () => {
  test.each(['true', 'TRUE', 'True'])('accepts %s', value => {
    expect(isWechatCodeFlowEnabled(value)).toBe(true);
  });

  test.each(['false', '', 'yes', null, undefined])(
    'rejects %s',
    (value: string | null | undefined) => {
      expect(isWechatCodeFlowEnabled(value)).toBe(false);
    },
  );
});

describe('isWechatJsapiAvailable', () => {
  const available = {
    inWechatBrowser: true,
    enableWxcode: 'true',
    openId: 'o_test_openid',
  };

  test('allows JSAPI only with an openid in hand', () => {
    expect(isWechatJsapiAvailable(available)).toBe(true);
  });

  test.each([null, undefined, '', '   '])(
    'refuses JSAPI when the account openid is %p',
    (openId: string | null | undefined) => {
      expect(isWechatJsapiAvailable({ ...available, openId })).toBe(false);
    },
  );

  test('refuses JSAPI outside the WeChat browser', () => {
    expect(
      isWechatJsapiAvailable({ ...available, inWechatBrowser: false }),
    ).toBe(false);
  });

  test('refuses JSAPI when the code flow is disabled', () => {
    expect(
      isWechatJsapiAvailable({ ...available, enableWxcode: 'false' }),
    ).toBe(false);
  });
});
