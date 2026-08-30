'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Elements,
  PaymentElement,
  useElements,
  useStripe,
} from '@stripe/react-stripe-js';
import type { Stripe } from '@stripe/stripe-js';
import { Button } from '@/components/ui/Button';
import type { LearnerPaymentAttemptContext } from '@/lib/paymentAnalytics';
import { getStripeInstance } from '@/lib/stripe';
import { useTranslation } from 'react-i18next';

interface StripeCardFormProps {
  clientSecret?: string;
  publishableKey?: string;
  onAttempt: () => LearnerPaymentAttemptContext | undefined;
  onConfirmSuccess: (
    attempt?: LearnerPaymentAttemptContext,
  ) => Promise<void> | void;
  onError?: (
    message: string,
    status: 'failed' | 'pending',
    attempt?: LearnerPaymentAttemptContext,
  ) => void;
}

const StripeFormInner = ({
  onAttempt,
  onConfirmSuccess,
  onError,
}: Pick<StripeCardFormProps, 'onAttempt' | 'onConfirmSuccess' | 'onError'>) => {
  const stripe = useStripe();
  const elements = useElements();
  const { t } = useTranslation();
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!stripe || !elements || submitting) {
      return;
    }
    setSubmitting(true);
    try {
      let attempt: LearnerPaymentAttemptContext | undefined;
      try {
        attempt = onAttempt();
      } catch {}
      const result = await stripe.confirmPayment({
        elements,
        redirect: 'if_required',
      });

      if (result.error) {
        onError?.(
          result.error.message || t('module.pay.stripeError'),
          'failed',
          attempt,
        );
        return;
      }

      if (result.paymentIntent) {
        const status = result.paymentIntent.status;
        if (status === 'succeeded') {
          await onConfirmSuccess(attempt);
        } else if (status === 'processing') {
          onError?.(t('module.pay.stripeProcessing'), 'pending', attempt);
        } else if (status === 'requires_payment_method') {
          onError?.(t('module.pay.stripeRequiresMethod'), 'failed', attempt);
        }
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className='space-y-4'
    >
      <PaymentElement />
      <Button
        type='submit'
        disabled={!stripe || submitting}
        className='w-full'
      >
        {submitting ? t('module.pay.processing') : t('module.pay.pay')}
      </Button>
    </form>
  );
};

export const StripeCardForm = ({
  clientSecret,
  publishableKey,
  onAttempt,
  onConfirmSuccess,
  onError,
}: StripeCardFormProps) => {
  const [stripePromise, setStripePromise] =
    useState<Promise<Stripe | null> | null>(null);
  const { t } = useTranslation();

  useEffect(() => {
    if (!publishableKey) {
      setStripePromise(null);
      return;
    }
    setStripePromise(getStripeInstance(publishableKey));
  }, [publishableKey]);

  const elementsOptions = useMemo(() => {
    if (!clientSecret) {
      return undefined;
    }
    return {
      clientSecret,
    };
  }, [clientSecret]);

  if (!publishableKey) {
    return (
      <div className='text-sm text-muted-foreground'>
        {t('module.pay.stripeMissingPublishableKey')}
      </div>
    );
  }

  if (!clientSecret || !stripePromise || !elementsOptions) {
    return (
      <div className='text-sm text-muted-foreground'>
        {t('module.pay.stripeAwaitingIntent')}
      </div>
    );
  }

  return (
    <Elements
      stripe={stripePromise}
      options={elementsOptions}
    >
      <StripeFormInner
        onAttempt={onAttempt}
        onConfirmSuccess={onConfirmSuccess}
        onError={onError}
      />
    </Elements>
  );
};

export default StripeCardForm;
