'use client';

import type { ComponentProps, ComponentType } from 'react';
import type { PaymentAction } from '@/types/payment';
import StripeCardForm from './StripeCardForm';

export type PaymentSdkFormProps = Omit<
  ComponentProps<typeof StripeCardForm>,
  'clientSecret'
> & {
  action: Extract<PaymentAction, { type: 'sdk_confirm' }>;
};

const StripePaymentSdk = ({
  action,
  publishableKey,
  ...callbacks
}: PaymentSdkFormProps) => (
  <StripeCardForm
    {...callbacks}
    clientSecret={action.client_secret}
    publishableKey={action.publishable_key || publishableKey}
  />
);

const handlers = new Map<string, ComponentType<PaymentSdkFormProps>>([
  ['stripe', StripePaymentSdk],
]);

/** Register integrations during application setup, before payment views mount. */
export function registerPaymentSdkHandler(
  sdk: string,
  handler: ComponentType<PaymentSdkFormProps>,
): () => void {
  if (!sdk.trim() || handlers.has(sdk)) {
    throw new Error('Payment SDK handler must have a unique nonempty name');
  }
  handlers.set(sdk, handler);
  return () => {
    if (handlers.get(sdk) === handler) handlers.delete(sdk);
  };
}

export function hasPaymentSdkHandler(sdk: string): boolean {
  return handlers.has(sdk);
}

export default function PaymentSdkForm(props: PaymentSdkFormProps) {
  const Handler = handlers.get(props.action.sdk);
  return Handler ? <Handler {...props} /> : null;
}
