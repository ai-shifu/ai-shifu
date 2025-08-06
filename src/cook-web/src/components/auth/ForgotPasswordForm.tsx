'use client';

import { useState } from 'react';
import { ForgotPasswordCombined } from '@/components/auth/ForgotPasswordCombined';
import { ForgotPasswordReset } from '@/components/auth/ForgotPasswordReset';
import { useToast } from '@/hooks/useToast';
import { useTranslation } from 'react-i18next';
interface ForgotPasswordFormProps {
  onComplete: () => void;
}

export function ForgotPasswordForm({ onComplete }: ForgotPasswordFormProps) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [step, setStep] = useState<'verify' | 'reset'>('verify');
  const [email, setEmail] = useState('');

  const handleVerifyNext = (email: string) => {
    setEmail(email);
    setStep('reset');
  };

  const handleComplete = () => {
    toast({
      title: t('auth.passwordReset'),
      description: t('auth.pleaseUseNewPassword'),
    });
    onComplete();
  };

  return (
    <div className='space-y-4'>
      {step === 'verify' && (
        <ForgotPasswordCombined onNext={handleVerifyNext} />
      )}

      {step === 'reset' && (
        <ForgotPasswordReset
          email={email}
          onBack={() => setStep('verify')}
          onComplete={handleComplete}
        />
      )}
    </div>
  );
}
