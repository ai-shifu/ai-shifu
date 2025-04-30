'use client';

import { useState } from 'react';
import { ForgotPasswordCombined } from '@/components/auth/forgot-password-combined';
import { ForgotPasswordReset } from '@/components/auth/forgot-password-reset';
import { useToast } from '@/hooks/use-toast';

interface ForgotPasswordFormProps {
  onComplete: () => void;
}

export function ForgotPasswordForm({ onComplete }: ForgotPasswordFormProps) {
  const { toast } = useToast();
  const [step, setStep] = useState<'verify' | 'reset'>('verify');
  const [email, setEmail] = useState('');

  const handleVerifyNext = (email: string) => {
    setEmail(email);
    setStep('reset');
  };

  const handleComplete = () => {
    toast({
      title: '密码已重置',
      description: '请使用新密码登录',
    });
    onComplete();
  };

  return (
    <div className="space-y-4">
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
