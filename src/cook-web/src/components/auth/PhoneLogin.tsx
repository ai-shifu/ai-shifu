'use client';

import type React from 'react';

import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Loader2 } from 'lucide-react';
import { useToast } from '@/hooks/useToast';
import { TermsCheckbox } from '@/components/TermsCheckbox';
import { TermsConfirmDialog } from '@/components/auth/TermsConfirmDialog';
import { ImageCaptchaInput } from '@/components/auth/ImageCaptchaInput';
import { isValidPhoneNumber } from '@/lib/validators';
import { useTranslation } from 'react-i18next';
import i18n from '@/i18n';
import { useAuth } from '@/hooks/useAuth';
import { useCaptchaTicket } from '@/hooks/useCaptchaTicket';
import { cn } from '@/lib/utils';

import type { UserInfo } from '@/c-types';
interface PhoneLoginProps {
  onLoginSuccess: (userInfo: UserInfo) => void;
  loginContext?: string;
  courseId?: string;
}

export function PhoneLogin({
  onLoginSuccess,
  loginContext,
  courseId,
}: PhoneLoginProps) {
  const { toast } = useToast();
  const [isLoading, setIsLoading] = useState(false);
  const [phoneNumber, setPhoneNumber] = useState('');
  const [phoneOtp, setPhoneOtp] = useState('');
  const [showOtpInput, setShowOtpInput] = useState(false);
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [phoneError, setPhoneError] = useState('');
  const [captchaError, setCaptchaError] = useState('');
  const [showTermsDialog, setShowTermsDialog] = useState(false);
  const { t } = useTranslation();
  const { loginWithSmsCode, sendSmsCode } = useAuth({
    onSuccess: onLoginSuccess,
    loginContext,
    courseId,
  });
  const {
    captchaImage,
    captchaCode,
    setCaptchaCode,
    isCaptchaLoading,
    refreshCaptcha,
    verifyCaptcha,
  } = useCaptchaTicket();

  const startOtpFlow = () => {
    setShowOtpInput(true);
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

  const isSmsRateLimitedError = (error: unknown) => {
    if (!(error instanceof Error)) {
      return false;
    }
    const code =
      typeof (error as { code?: unknown }).code === 'number'
        ? Number((error as { code?: unknown }).code)
        : NaN;
    return (
      code === 9999 && error.message === t('server.user.smsSendTooFrequent')
    );
  };

  const validatePhone = (phone: string) => {
    if (!phone) {
      setPhoneError(t('module.auth.phoneEmpty'));
      return false;
    }

    if (!isValidPhoneNumber(phone)) {
      setPhoneError(t('module.auth.phoneError'));
      return false;
    }

    setPhoneError('');
    return true;
  };

  const handlePhoneChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setPhoneNumber(value);
    if (value) {
      validatePhone(value);
    } else {
      setPhoneError('');
    }
  };

  // Normalize OTP to prevent iOS Safari double-paste (e.g., 12341234)
  const normalizeOtp = (rawValue: string) => {
    const digits = rawValue.replace(/\D/g, '');
    if (!digits) {
      return '';
    }
    const maxLength = 4;
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

  const handleOtpChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPhoneOtp(normalizeOtp(e.target.value));
  };

  const refreshCaptchaSilently = async () => {
    try {
      await refreshCaptcha();
    } catch {
      // The API request layer displays failures; keep the current UI stable.
    }
  };

  const getCaptchaTicket = async () => {
    if (!captchaCode.trim()) {
      setCaptchaError(t('module.auth.captchaRequired'));
      toast({
        title: t('module.auth.captchaRequired'),
        variant: 'destructive',
      });
      return '';
    }

    try {
      setCaptchaError('');
      return await verifyCaptcha();
    } catch (error: any) {
      const message = error?.message || t('module.auth.captchaVerifyFailed');
      setCaptchaError(message);
      toast({
        title: t('module.auth.captchaVerifyFailed'),
        description: message,
        variant: 'destructive',
      });
      await refreshCaptchaSilently();
      return '';
    }
  };

  const doSendSmsCode = async () => {
    try {
      setIsLoading(true);

      const captchaTicket = await getCaptchaTicket();
      if (!captchaTicket) {
        return;
      }

      const response = await sendSmsCode(phoneNumber, captchaTicket);

      if (response.code == 0) {
        startOtpFlow();
        void refreshCaptchaSilently();
        toast({
          title: t('module.auth.sendSuccess'),
          description: t('module.auth.checkYourSms'),
        });
      }
    } catch (error) {
      if (isSmsRateLimitedError(error)) {
        startOtpFlow();
        void refreshCaptchaSilently();
        toast({
          title: t('module.auth.checkYourSms'),
          description: t('server.user.smsSendTooFrequent'),
        });
        return;
      }
      void refreshCaptchaSilently();
      // Error already handled in sendSmsCode
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendOtp = async () => {
    if (!validatePhone(phoneNumber)) {
      return;
    }

    if (!termsAccepted) {
      setShowTermsDialog(true);
      return;
    }

    await doSendSmsCode();
  };

  const handleVerifyOtp = async () => {
    if (!phoneOtp) {
      toast({
        title: t('module.auth.otpError'),
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
      await loginWithSmsCode(phoneNumber, phoneOtp, i18n.language);
    } finally {
      setIsLoading(false);
    }
  };

  const handleOtpKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && showOtpInput && phoneOtp && !isLoading) {
      e.preventDefault();
      handleVerifyOtp();
    }
  };

  const handleTermsConfirm = async () => {
    setTermsAccepted(true);
    setShowTermsDialog(false);
    // Auto send SMS code after terms accepted, but only if OTP input is not already shown
    if (!showOtpInput) {
      await doSendSmsCode();
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
            htmlFor='phone'
            className={phoneError ? 'text-red-500' : ''}
          >
            {t('module.auth.phone')}
          </Label>
          <Input
            id='phone'
            placeholder={t('module.auth.phonePlaceholder')}
            value={phoneNumber}
            onChange={handlePhoneChange}
            disabled={isLoading}
            className={cn(
              'text-base sm:text-sm',
              phoneError &&
                'border-red-500 focus-visible:ring-red-500 placeholder:text-muted-foreground',
            )}
          />
          {phoneError && <p className='text-xs text-red-500'>{phoneError}</p>}
        </div>

        <ImageCaptchaInput
          value={captchaCode}
          image={captchaImage}
          isLoading={isCaptchaLoading}
          disabled={isLoading}
          error={captchaError}
          onChange={value => {
            setCaptchaCode(value);
            if (captchaError) {
              setCaptchaError('');
            }
          }}
          onRefresh={() => {
            setCaptchaError('');
            void refreshCaptchaSilently();
          }}
        />

        <div className='flex space-x-2'>
          <div className='flex-1'>
            <Input
              id='otp'
              type='text'
              placeholder={t('module.auth.otpPlaceholder')}
              value={phoneOtp}
              onChange={handleOtpChange}
              onKeyDown={handleOtpKeyDown}
              disabled={isLoading || !showOtpInput}
              inputMode='numeric'
              autoComplete='one-time-code'
              name='one-time-code'
              pattern='[0-9]*'
              enterKeyHint='done'
              className='text-base sm:text-sm'
            />
          </div>
          <Button
            onClick={handleSendOtp}
            disabled={
              isLoading ||
              isCaptchaLoading ||
              countdown > 0 ||
              !phoneNumber ||
              !!phoneError ||
              !captchaCode.trim()
            }
            className='whitespace-nowrap h-8'
          >
            {isLoading && !showOtpInput ? (
              <Loader2 className='h-4 w-4 animate-spin mr-2' />
            ) : countdown > 0 ? (
              t('module.auth.secondsLater', { count: countdown })
            ) : (
              t('module.auth.getOtp')
            )}
          </Button>
        </div>

        <div className='mt-2'>
          <TermsCheckbox
            checked={termsAccepted}
            onCheckedChange={setTermsAccepted}
            disabled={isLoading}
          />
        </div>

        {showOtpInput && (
          <Button
            className='w-full h-8'
            onClick={handleVerifyOtp}
            disabled={isLoading || !phoneOtp}
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
