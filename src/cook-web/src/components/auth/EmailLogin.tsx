'use client';

import type React from 'react';

import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { useToast } from '@/hooks/use-toast';
import { Loader2 } from 'lucide-react';
import { TermsCheckbox } from '@/components/TermsCheckbox';
import apiService from '@/api';
import { isValidEmail } from '@/lib/validators';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/hooks/useAuth';

import type { UserInfo } from '@/c-types';

interface EmailLoginProps {
  onLoginSuccess: (userInfo: UserInfo) => void;
  onForgotPassword: () => void;
}

export function EmailLogin({
  onLoginSuccess,
  onForgotPassword,
}: EmailLoginProps) {
  const { toast } = useToast();
  const [isLoading, setIsLoading] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [emailError, setEmailError] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const { t } = useTranslation();
  const { loginWithEmailPassword } = useAuth({ onSuccess: onLoginSuccess });

  const validateEmail = (email: string) => {
    if (!email) {
      setEmailError(t('auth.email-empty'));
      return false;
    }

    if (!isValidEmail(email)) {
      setEmailError(t('auth.email-error'));
      return false;
    }

    setEmailError('');
    return true;
  };

  const validatePassword = (password: string) => {
    if (!password) {
      setPasswordError(t('auth.password-error'));
      return false;
    }

    setPasswordError('');
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

  const handlePasswordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setPassword(value);
    if (value) {
      validatePassword(value);
    } else {
      setPasswordError('');
    }
  };

  const handlePasswordLogin = async () => {
    const isEmailValid = validateEmail(email);
    const isPasswordValid = validatePassword(password);

    if (!isEmailValid || !isPasswordValid) {
      return;
    }

    if (!termsAccepted) {
      toast({
        title: t('auth.terms-error'),
        variant: 'destructive',
      });
      return;
    }

    try {
      setIsLoading(true);
      const username = email;
      await loginWithEmailPassword(username, password);
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
          placeholder={t('auth.email-placeholder')}
          value={email}
          onChange={handleEmailChange}
          disabled={isLoading}
          className={
            emailError ? 'border-red-500 focus-visible:ring-red-500' : ''
          }
        />
        {emailError && <p className='text-xs text-red-500'>{emailError}</p>}
      </div>
      <div className='space-y-2'>
        <div className='flex items-center justify-between'>
          <Label
            htmlFor='password'
            className={passwordError ? 'text-red-500' : ''}
          >
            {t('auth.password')}
          </Label>
          <button
            type='button'
            onClick={onForgotPassword}
            className='text-primary text-sm hover:underline'
          >
            {t('auth.forgot-password')}
          </button>
        </div>
        <Input
          id='password'
          type='password'
          placeholder={t('auth.password-placeholder')}
          value={password}
          onChange={handlePasswordChange}
          disabled={isLoading}
          className={
            passwordError ? 'border-red-500 focus-visible:ring-red-500' : ''
          }
        />
        {passwordError && (
          <p className='text-xs text-red-500'>{passwordError}</p>
        )}
      </div>
      <TermsCheckbox
        checked={termsAccepted}
        onCheckedChange={setTermsAccepted}
        disabled={isLoading}
      />
      <Button
        className='w-full h-8'
        onClick={handlePasswordLogin}
        disabled={
          isLoading || !email || !password || !!emailError || !!passwordError
        }
      >
        {isLoading ? <Loader2 className='h-4 w-4 animate-spin mr-2' /> : null}
        {t('auth.login')}
      </Button>
    </div>
  );
}
