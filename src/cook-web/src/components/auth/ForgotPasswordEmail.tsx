'use client';

import type React from 'react';

import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { useToast } from '@/hooks/useToast';
import { Loader2 } from 'lucide-react';
import apiService from '@/api';
import { isValidEmail } from '@/lib/validators';
import { useTranslation } from 'react-i18next';
import i18n from '@/i18n';
interface ForgotPasswordEmailProps {
  onNext: (email: string) => void;
}

export function ForgotPasswordEmail({ onNext }: ForgotPasswordEmailProps) {
  const { toast } = useToast();
  const { t } = useTranslation();
  const [isLoading, setIsLoading] = useState(false);
  const [email, setEmail] = useState('');
  const [emailError, setEmailError] = useState('');

  const validateEmail = (email: string) => {
    if (!email) {
      setEmailError(t('auth.emailError'));
      return false;
    }

    if (!isValidEmail(email)) {
      setEmailError(t('auth.emailError'));
      return false;
    }

    setEmailError('');
    return true;
  };

  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setEmail(value);
    if (value) {
      validateEmail(value);
    } else {
      setEmailError('');
    }
  };

  const handleSendOtp = async () => {
    if (!validateEmail(email)) {
      return;
    }

    try {
      setIsLoading(true);

      const response = await apiService.sendMailCode({
        mail: email,
        language: i18n.language,
      });

      if (response.code == 0) {
        toast({
          title: t('auth.sendSuccess'),
          description: t('auth.checkYourEmail'),
        });
        onNext(email);
      } else {
        toast({
          title: t('auth.sendFailed'),
          description: t('common.pleaseTryAgainLater'),
          variant: 'destructive',
        });
      }
    } catch (error: any) {
      toast({
        title: t('auth.sendFailed'),
        description: error.message || t('common.networkError'),
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className='space-y-4'>
      <div className='space-y-2'>
        <Label
          htmlFor='email'
          className={emailError ? 'text-red-500' : ''}
        >
          {t('auth.email')}
        </Label>
        <Input
          id='email'
          type='email'
          placeholder={t('auth.emailPlaceholder')}
          value={email}
          onChange={handleEmailChange}
          disabled={isLoading}
          className={
            emailError ? 'border-red-500 focus-visible:ring-red-500' : ''
          }
        />
        {emailError && <p className='text-xs text-red-500'>{emailError}</p>}
      </div>

      <Button
        className='w-full h-8'
        onClick={handleSendOtp}
        disabled={isLoading || !email || !!emailError}
      >
        {isLoading ? <Loader2 className='h-4 w-4 animate-spin mr-2' /> : null}
        {t('auth.getOtp')}
      </Button>
    </div>
  );
}
