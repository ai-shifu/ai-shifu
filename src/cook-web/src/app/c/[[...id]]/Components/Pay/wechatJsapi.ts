/**
 * WeChat JSAPI payment availability.
 *
 * JSAPI charges are rejected by the payment gateway without an openid bound to
 * the paying account. The code flow that grants one is disabled on custom
 * domains, and even where it is enabled the binding can be missing (the OAuth
 * code is single-use and may have been spent by guest registration), so the
 * openid itself has to be checked rather than assumed.
 */

export const isWechatCodeFlowEnabled = (
  enableWxcode: string | null | undefined,
): boolean =>
  typeof enableWxcode === 'string' && enableWxcode.toLowerCase() === 'true';

export const isWechatJsapiAvailable = ({
  inWechatBrowser,
  enableWxcode,
  openId,
}: {
  inWechatBrowser: boolean;
  enableWxcode: string | null | undefined;
  openId: string | null | undefined;
}): boolean =>
  inWechatBrowser && isWechatCodeFlowEnabled(enableWxcode) && Boolean(openId);
