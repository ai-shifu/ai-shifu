'use client';

import type React from 'react';

import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Loader2 } from 'lucide-react';
import { useToast } from '@/hooks/useToast';
import { TermsCheckbox } from '@/components/TermsCheckbox';
import { TermsConfirmDialog } from '@/components/auth/TermsConfirmDialog';
import { isValidEmail } from '@/lib/validators';
import { useTranslation } from 'react-i18next';
import i18n from '@/i18n';
import { useAuth } from '@/hooks/useAuth';
import { cn } from '@/lib/utils';

import type { UserInfo } from '@/c-types';

interface EmailLoginProps {
  onLoginSuccess: (userInfo: UserInfo) => void;
}

export function EmailLogin({ onLoginSuccess }: EmailLoginProps) {
  const { toast } = useToast();
  const [isLoading, setIsLoading] = useState(false);
  const [email, setEmail] = useState('');
  const [emailCode, setEmailCode] = useState('');
  const [showCodeInput, setShowCodeInput] = useState(false);
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [emailError, setEmailError] = useState('');
  const [showTermsDialog, setShowTermsDialog] = useState(false);
  const previousCountdownRef = useRef(0);
  const { t } = useTranslation();
  const { loginWithEmailCode, sendEmailCode } = useAuth({
    onSuccess: onLoginSuccess,
  });

  const startCountdown = () => {
    setShowCodeInput(true);
    setCountdown(60);
    const timer = setInterval(() => {
      setCountdown(prevCountdown => {
        if (prevCountdown <= 1) {
          clearInterval(timer);
          return 0;
        }
        return prevCountdown - 1;
      });
    }, 1000);
  };

  const isEmailRateLimitedError = (error: unknown) => {
    if (!(error instanceof Error)) {
      return false;
    }
    const code =
      typeof (error as { code?: unknown }).code === 'number'
        ? Number((error as { code?: unknown }).code)
        : NaN;
    return (
      code === 9999 && error.message === t('server.user.emailSendTooFrequent')
    );
  };

  const validateEmail = (value: string) => {
    if (!value) {
      setEmailError(t('module.auth.emailEmpty'));
      return false;
    }

    if (!isValidEmail(value)) {
      setEmailError(t('module.auth.emailError'));
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

  // Normalize code to prevent double-paste
  const normalizeCode = (rawValue: string) => {
    const digits = rawValue.replace(/\D/g, '');
    if (!digits) {
      return '';
    }
    const maxLength = 6;
    const capped = digits.slice(0, maxLength * 2);
    const primary = capped.slice(0, maxLength);
    if (capped.length > maxLength) {
      const duplicateCandidate = capped.slice(maxLength, maxLength * 2);
      if (duplicateCandidate === primary) {
        return primary;
      }
    }
    return primary;
  };

  const handleCodeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setEmailCode(normalizeCode(e.target.value));
  };

  const handleCodeKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && showCodeInput && emailCode && !isLoading) {
      e.preventDefault();
      handleVerifyCode();
    }
  };

  useEffect(() => {
    previousCountdownRef.current = countdown;
  }, [countdown]);

  const doSendCode = async () => {
    try {
      setIsLoading(true);

      const response = await sendEmailCode(email);

      if (response.code === 0) {
        startCountdown();
        toast({
          title: t('module.auth.sendSuccess'),
          description: t('module.auth.checkYourEmail'),
        });
      }
    } catch (error) {
      if (isEmailRateLimitedError(error)) {
        startCountdown();
        toast({
          title: t('module.auth.checkYourEmail'),
          description: t('server.user.emailSendTooFrequent'),
        });
        return;
      }
      // Error already handled in sendEmailCode
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendCode = async () => {
    if (!validateEmail(email)) {
      return;
    }

    if (!termsAccepted) {
      setShowTermsDialog(true);
      return;
    }

    await doSendCode();
  };

  const handleVerifyCode = async () => {
    const code = emailCode.trim();

    if (!code) {
      toast({
        title: t('module.auth.codeRequired'),
        variant: 'destructive',
      });
      return;
    }

    if (!termsAccepted) {
      setShowTermsDialog(true);
      return;
    }

    try {
      setIsLoading(true);
      await loginWithEmailCode(email, code, i18n.language);
    } finally {
      setIsLoading(false);
    }
  };

  const handleTermsConfirm = async () => {
    setTermsAccepted(true);
    setShowTermsDialog(false);
    // Auto send email code after terms accepted, but only if code input is not already shown
    if (!showCodeInput) {
      await doSendCode();
    }
  };

  const handleTermsCancel = () => {
    setShowTermsDialog(false);
  };

  return (
    <>
      <TermsConfirmDialog
        open={showTermsDialog}
        onOpenChange={setShowTermsDialog}
        onConfirm={handleTermsConfirm}
        onCancel={handleTermsCancel}
      />
      <div className='space-y-4'>
        <div className='space-y-2'>
          <Label
            htmlFor='email-login'
            className={emailError ? 'text-red-500' : ''}
          >
            {t('module.auth.email')}
          </Label>
          <Input
            id='email-login'
            type='email'
            placeholder={t('module.auth.emailPlaceholder')}
            value={email}
            onChange={handleEmailChange}
            disabled={isLoading || showCodeInput}
            autoComplete='email'
            className={cn(
              'text-base sm:text-sm',
              emailError &&
                'border-red-500 focus-visible:ring-red-500 placeholder:text-muted-foreground',
            )}
          />
          {emailError && <p className='text-xs text-red-500'>{emailError}</p>}
        </div>

        <div className='space-y-2'>
          <Label htmlFor='email-code'>
            {t('module.auth.verificationCode')}
          </Label>
          <div className='flex space-x-2'>
            <div className='flex-1'>
              <Input
                id='email-code'
                type='text'
                placeholder={t('module.auth.codePlaceholder')}
                value={emailCode}
                onChange={handleCodeChange}
                onKeyDown={handleCodeKeyDown}
                disabled={isLoading || !showCodeInput}
                inputMode='numeric'
                autoComplete='one-time-code'
                name='one-time-code'
                pattern='[0-9]*'
                enterKeyHint='done'
                className='text-base sm:text-sm'
              />
            </div>
            <Button
              onClick={handleSendCode}
              disabled={isLoading || countdown > 0 || !email || !!emailError}
              className='h-8 min-w-[100px] px-2 whitespace-nowrap'
            >
              {isLoading && !showCodeInput ? (
                <Loader2 className='h-4 w-4 animate-spin mr-2' />
              ) : countdown > 0 ? (
                t('module.auth.secondsLater', { count: countdown })
              ) : (
                t('module.auth.getCode')
              )}
            </Button>
          </div>
        </div>

        <div className='mt-2'>
          <TermsCheckbox
            checked={termsAccepted}
            onCheckedChange={setTermsAccepted}
            disabled={isLoading}
          />
        </div>

        {showCodeInput && (
          <Button
            className='w-full h-8'
            onClick={handleVerifyCode}
            disabled={isLoading || !emailCode}
          >
            {isLoading ? (
              <Loader2 className='h-4 w-4 animate-spin mr-2' />
            ) : null}
            {t('module.auth.login')}
          </Button>
        )}
      </div>
    </>
  );
}
