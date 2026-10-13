/** Interpret payment actions once and isolate compatibility with old APIs. */
import type {
  PaymentAction,
  PaymentContract,
  PaymentOption,
} from '@/types/payment';

type LegacyPaymentResult = PaymentContract & {
  provider?: string;
  payment_channel?: string;
  channel?: string;
  qr_url?: unknown;
  redirect_url?: string;
  checkout_session_id?: string;
  payment_payload?: object | null;
};

function validPaymentUrl(
  value: unknown,
  type: 'qr' | 'redirect',
): value is string {
  if (typeof value !== 'string' || !value.trim()) return false;
  // QR content is opaque data. Only browser navigation requires a URL scheme.
  if (type === 'qr') return true;
  try {
    const url = new URL(value);
    return url.protocol === 'http:' || url.protocol === 'https:';
  } catch {
    return false;
  }
}

/** Preserve existing mobile wallet launches; other QR content is rendered only. */
export function canOpenPaymentQr(value: string): boolean {
  try {
    return ['http:', 'https:', 'weixin:', 'alipay:', 'alipays:'].includes(
      new URL(value).protocol,
    );
  } catch {
    return false;
  }
}

function validAction(value: unknown): PaymentAction | null {
  if (!value || typeof value !== 'object') return null;
  const action = value as Record<string, unknown>;
  if (action.type === 'none') return { type: 'none' };
  if (
    (action.type === 'qr' || action.type === 'redirect') &&
    validPaymentUrl(action.url, action.type)
  ) {
    return action as PaymentAction;
  }
  if (
    action.type === 'jsapi' &&
    action.parameters &&
    typeof action.parameters === 'object' &&
    ['appId', 'timeStamp', 'nonceStr', 'package', 'signType', 'paySign'].every(
      key =>
        typeof (action.parameters as Record<string, unknown>)[key] ===
          'string' &&
        Boolean((action.parameters as Record<string, unknown>)[key]),
    )
  ) {
    return action as PaymentAction;
  }
  if (
    action.type === 'sdk_confirm' &&
    typeof action.sdk === 'string' &&
    action.sdk.trim() &&
    typeof action.client_secret === 'string' &&
    action.client_secret.trim()
  ) {
    return action as PaymentAction;
  }
  return null;
}

export function resolvePaymentAction(
  result: LegacyPaymentResult,
): PaymentAction | null {
  if (result.payment_contract_version !== undefined) {
    // An unknown new action must never be reinterpreted as a legacy QR.
    return result.payment_contract_version === 1
      ? validAction(result.payment_action)
      : null;
  }
  const payload = (result.payment_payload || {}) as Record<string, unknown>;
  const provider = result.provider || result.payment_channel;
  const redirect = result.redirect_url || payload.checkout_session_url;
  if (redirect) {
    if (!validPaymentUrl(redirect, 'redirect')) return null;
    return {
      type: 'redirect',
      url: redirect,
      session_id: result.checkout_session_id,
    };
  }
  if (
    provider === 'stripe' &&
    typeof payload.client_secret === 'string' &&
    payload.client_secret
  ) {
    return {
      type: 'sdk_confirm',
      sdk: 'stripe',
      client_secret: payload.client_secret,
    };
  }
  if (
    payload.mode === 'jsapi' &&
    payload.jsapi_params &&
    typeof payload.jsapi_params === 'object'
  ) {
    return {
      type: 'jsapi',
      parameters: payload.jsapi_params as Record<string, string>,
    };
  }
  const credential = payload.credential as Record<string, unknown> | undefined;
  const url =
    result.qr_url || payload.qr_url || credential?.[result.channel || ''];
  if (url && typeof url === 'object' && result.channel === 'wx_pub') {
    return { type: 'jsapi', parameters: url as Record<string, string> };
  }
  if (typeof url === 'string' && url) {
    const type = provider === 'stripe' ? 'redirect' : 'qr';
    return validPaymentUrl(url, type) ? { type, url } : null;
  }
  return null;
}

export function resolvePaymentOption(
  options: readonly PaymentOption[] | undefined,
  channel: string,
): PaymentOption | undefined {
  const exact = options?.find(
    option => option.id === channel || option.channel === channel,
  );
  if (exact) return exact;
  // Old browser hints describe a method/scene, not a gateway identity.
  const hints: Record<string, [string, string]> = {
    alipay_qr: ['alipay', 'qr'],
    wx_pub_qr: ['wechat', 'qr'],
    wx_pub: ['wechat', 'wechat'],
    stripe: ['hosted', 'hosted'],
  };
  const hint = hints[channel];
  return hint
    ? options?.find(
        option => option.method === hint[0] && option.scene === hint[1],
      ) ||
        (channel === 'stripe'
          ? options?.find(option => option.method === 'card')
          : undefined)
    : undefined;
}

export function hasPaymentMethod(
  options: readonly PaymentOption[] | undefined,
  method: string,
): boolean {
  return Boolean(options?.some(option => option.method === method));
}

export function isProviderManaged(
  options: readonly PaymentOption[] | undefined,
  provider: string,
): boolean | undefined {
  if (!options) return undefined;
  return options.some(
    option =>
      option.provider === provider &&
      option.billing_mode === 'provider_managed',
  );
}

/** Preserve legacy hints while disambiguating routes shared by two integrations. */
export function paymentSelectionKey(
  option: PaymentOption,
  options: readonly PaymentOption[],
): string {
  return options.filter(item => item.channel === option.channel).length > 1 ||
    option.scene === 'hosted' ||
    option.scene === 'embedded'
    ? option.id
    : option.channel;
}

/** Keep one existing default hosted scene per integration. */
export function hostedPaymentOptions(
  options?: readonly PaymentOption[],
): PaymentOption[] {
  const hosted =
    options?.filter(
      option =>
        ['redirect', 'sdk_confirm'].includes(option.action) &&
        !['wechat', 'alipay'].includes(option.method),
    ) || [];
  return hosted.filter(
    (option, index) =>
      hosted.findIndex(item => item.provider === option.provider) === index,
  );
}

/** Preserve provider-owned defaults and retain identity when routes share names. */
export function defaultPaymentSelection(
  options: readonly PaymentOption[],
  wechatJsapiAvailable: boolean,
): string | undefined {
  const option =
    options.find(item => item.prefer_in_wechat && wechatJsapiAvailable) ||
    options.find(item => item.action === 'qr') ||
    options[0];
  return option ? paymentSelectionKey(option, options) : undefined;
}

/** Keep legacy payload interpretation out of desktop and mobile business views. */
export function resolvePaymentPresentation(input: {
  action?: PaymentAction | null;
  provider?: string;
  channel?: string;
  legacyPayload?: Record<string, unknown>;
  legacyValue?: unknown;
}) {
  const payload = input.legacyPayload || {};
  const action =
    input.action !== undefined
      ? input.action
      : resolvePaymentAction({
          provider: input.provider,
          channel: input.channel,
          payment_payload: payload,
          qr_url: input.legacyValue,
        });
  return {
    action,
    hostedCheckoutUrl: action?.type === 'redirect' ? action.url : '',
    confirmationMode:
      action?.type === 'redirect'
        ? 'checkout_session'
        : action?.type === 'sdk_confirm'
          ? 'payment_intent'
          : '',
    stripeClientSecret:
      action?.type === 'sdk_confirm' && action.sdk === 'stripe'
        ? action.client_secret
        : undefined,
    jsapiParameters: action?.type === 'jsapi' ? action.parameters : undefined,
    checkoutSessionId:
      action?.type === 'redirect' && action.session_id
        ? action.session_id
        : typeof payload.checkout_session_id === 'string'
          ? payload.checkout_session_id
          : undefined,
  };
}

/** Old server hints are interpreted once while mixed-version clients remain supported. */
export function resolveRequestedPaymentProvider(
  options: readonly PaymentOption[] | undefined,
  selection: string,
  legacyChannels: readonly string[],
): string | undefined {
  if (options) return resolvePaymentOption(options, selection)?.provider;
  if (selection.startsWith('stripe')) return 'stripe';
  if (selection === 'alipay_qr')
    return legacyChannels.includes('alipay') ? 'alipay' : 'pingxx';
  if (selection === 'wx_pub' || selection === 'wx_pub_qr')
    return legacyChannels.includes('wechatpay') ? 'wechatpay' : 'pingxx';
  return undefined;
}

const isJsapiParams = (value: unknown): value is Record<string, string> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return false;
  }
  return Object.values(value).every(item => typeof item === 'string');
};

export const resolveJsapiParams = (
  qrUrl: unknown,
  paymentPayload: {
    jsapi_params?: Record<string, string>;
    credential?: Record<string, unknown>;
  },
) => {
  if (isJsapiParams(paymentPayload.jsapi_params)) {
    return paymentPayload.jsapi_params;
  }
  const credential = paymentPayload.credential || {};
  const wxPubCredential = credential.wx_pub;
  if (isJsapiParams(wxPubCredential)) {
    return wxPubCredential;
  }
  if (isJsapiParams(qrUrl)) {
    return qrUrl;
  }
  return null;
};
