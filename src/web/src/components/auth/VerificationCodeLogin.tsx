'use client';

import type React from 'react';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';

import type { UserInfo } from '@/c-types';
import { ImageCaptchaInput } from '@/components/auth/ImageCaptchaInput';
import { TermsConfirmDialog } from '@/components/auth/TermsConfirmDialog';
import { TermsCheckbox } from '@/components/TermsCheckbox';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { useAuth } from '@/hooks/useAuth';
import { useCaptchaTicket } from '@/hooks/useCaptchaTicket';
import { useToast } from '@/hooks/useToast';
import i18n from '@/i18n';
import type { ContactMode } from '@/lib/resolve-contact-mode';
import { cn } from '@/lib/utils';
import { isValidEmail, isValidPhoneNumber } from '@/lib/validators';
import type { ReferralLoginMetadata } from '@/types/referral';

const VERIFICATION_CODE_LENGTH = 4;
const VERIFICATION_CODE_COOLDOWN_SECONDS = 60;

type VerificationCodeLoginProps = {
  mode: ContactMode;
  onLoginSuccess: (userInfo: UserInfo) => void;
  loginContext?: string;
  courseId?: string;
  referralMetadata?: ReferralLoginMetadata;
};

const normalizeVerificationCode = (rawValue: string): string => {
  const digits = rawValue.replace(/\D/g, '');
  if (!digits) {
    return '';
  }

  const capped = digits.slice(0, VERIFICATION_CODE_LENGTH * 2);
  const primary = capped.slice(0, VERIFICATION_CODE_LENGTH);
  if (capped.length > VERIFICATION_CODE_LENGTH) {
    const duplicateCandidate = capped.slice(
      VERIFICATION_CODE_LENGTH,
      VERIFICATION_CODE_LENGTH * 2,
    );
    if (duplicateCandidate === primary) {
      return primary;
    }
  }
  return primary;
};

export function VerificationCodeLogin({
  mode,
  onLoginSuccess,
  loginContext,
  courseId,
  referralMetadata,
}: VerificationCodeLoginProps) {
  const isPhone = mode === 'phone';
  const { toast } = useToast();
  const { t } = useTranslation();
  const [isLoading, setIsLoading] = useState(false);
  const [identifier, setIdentifier] = useState('');
  const [verificationCode, setVerificationCode] = useState('');
  const [showCodeInput, setShowCodeInput] = useState(false);
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [identifierError, setIdentifierError] = useState('');
  const [captchaError, setCaptchaError] = useState('');
  const [showTermsDialog, setShowTermsDialog] = useState(false);
  const previousCountdownRef = useRef(0);
  const { loginWithSmsCode, loginWithEmailCode, sendSmsCode, sendEmailCode } =
    useAuth({
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
  } = useCaptchaTicket(isPhone);

  const identifierConfig = isPhone
    ? {
        id: 'phone',
        inputType: 'text',
        autoComplete: undefined,
        label: t('module.auth.phone'),
        placeholder: t('module.auth.phonePlaceholder'),
        emptyError: t('module.auth.phoneEmpty'),
        invalidError: t('module.auth.phoneError'),
        isValid: isValidPhoneNumber,
      }
    : {
        id: 'email-login',
        inputType: 'email',
        autoComplete: 'email',
        label: t('module.auth.email'),
        placeholder: t('module.auth.emailPlaceholder'),
        emptyError: t('module.auth.emailEmpty'),
        invalidError: t('module.auth.emailError'),
        isValid: isValidEmail,
      };
  const codeInputId = isPhone ? 'otp' : 'email-code';

  const startCountdown = useCallback(() => {
    setShowCodeInput(true);
    setCountdown(VERIFICATION_CODE_COOLDOWN_SECONDS);
  }, []);

  useEffect(() => {
    if (countdown <= 0) {
      return;
    }

    const timer = window.setTimeout(() => {
      setCountdown(current => Math.max(0, current - 1));
    }, 1000);

    return () => window.clearTimeout(timer);
  }, [countdown]);

  const resetCaptchaChallenge = useCallback(
    (options?: { clearError?: boolean }) => {
      if (!isPhone) {
        return;
      }
      setCaptchaCode('');
      if (options?.clearError) {
        setCaptchaError('');
      }
      void refreshCaptcha({ clearCode: false }).catch(() => {
        // The request layer reports failures; keep the current form usable.
      });
    },
    [isPhone, refreshCaptcha, setCaptchaCode],
  );

  useEffect(() => {
    if (isPhone && previousCountdownRef.current > 0 && countdown === 0) {
      resetCaptchaChallenge({ clearError: true });
    }
    previousCountdownRef.current = countdown;
  }, [countdown, isPhone, resetCaptchaChallenge]);

  const normalizeIdentifier = (value: string) =>
    isPhone ? value : value.trim();

  const validateIdentifier = (value: string): boolean => {
    const normalizedValue = normalizeIdentifier(value);
    if (!normalizedValue) {
      setIdentifierError(identifierConfig.emptyError);
      return false;
    }
    if (!identifierConfig.isValid(normalizedValue)) {
      setIdentifierError(identifierConfig.invalidError);
      return false;
    }
    setIdentifierError('');
    return true;
  };

  const handleIdentifierChange = (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const value = event.target.value;
    setIdentifier(value);
    if (!isPhone && showCodeInput && countdown === 0) {
      setShowCodeInput(false);
      setVerificationCode('');
    }
    if (value) {
      validateIdentifier(value);
    } else {
      setIdentifierError('');
    }
  };

  const getCaptchaTicket = async (): Promise<string> => {
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
    } catch (error: unknown) {
      const message =
        error instanceof Error
          ? error.message
          : t('module.auth.captchaVerifyFailed');
      setCaptchaError(message);
      resetCaptchaChallenge();
      toast({
        title: t('module.auth.captchaVerifyFailed'),
        description: message,
        variant: 'destructive',
      });
      return '';
    }
  };

  const doSendCode = async () => {
    try {
      setIsLoading(true);
      const normalizedIdentifier = normalizeIdentifier(identifier);
      if (!isPhone && normalizedIdentifier !== identifier) {
        setIdentifier(normalizedIdentifier);
      }
      let result: { rateLimited: boolean };
      if (isPhone) {
        const captchaTicket = await getCaptchaTicket();
        if (!captchaTicket) {
          return;
        }
        result = await sendSmsCode(normalizedIdentifier, captchaTicket);
      } else {
        result = await sendEmailCode(normalizedIdentifier);
      }

      startCountdown();
      const channelPrompt = isPhone
        ? t('module.auth.checkYourSms')
        : t('module.auth.checkYourEmail');
      const rateLimitMessage = isPhone
        ? t('server.user.smsSendTooFrequent')
        : t('server.user.emailSendTooFrequent');
      toast({
        title: result.rateLimited
          ? channelPrompt
          : t('module.auth.sendSuccess'),
        description: result.rateLimited ? rateLimitMessage : channelPrompt,
      });
    } catch {
      // useAuth already reports non-rate-limit failures.
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendCode = async () => {
    if (!validateIdentifier(identifier)) {
      return;
    }
    if (!termsAccepted) {
      setShowTermsDialog(true);
      return;
    }
    await doSendCode();
  };

  const handleVerifyCode = async () => {
    const code = verificationCode.trim();
    const normalizedIdentifier = normalizeIdentifier(identifier);
    if (!code) {
      toast({
        title: t('module.auth.verificationCodeRequired'),
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
      if (isPhone) {
        await loginWithSmsCode(
          normalizedIdentifier,
          code,
          i18n.language,
          referralMetadata,
        );
      } else {
        await loginWithEmailCode(
          normalizedIdentifier,
          code,
          i18n.language,
          referralMetadata,
        );
      }
    } catch {
      // useAuth already reports login failures.
    } finally {
      setIsLoading(false);
    }
  };

  const handleCodeKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (
      event.key === 'Enter' &&
      showCodeInput &&
      verificationCode &&
      !isLoading
    ) {
      event.preventDefault();
      void handleVerifyCode();
    }
  };

  const handleTermsConfirm = async () => {
    setTermsAccepted(true);
    setShowTermsDialog(false);
    if (!showCodeInput) {
      await doSendCode();
    }
  };

  return (
    <>
      <TermsConfirmDialog
        open={showTermsDialog}
        onOpenChange={setShowTermsDialog}
        onConfirm={handleTermsConfirm}
        onCancel={() => setShowTermsDialog(false)}
      />
      <div className='space-y-4'>
        <div className='space-y-2'>
          <Label
            htmlFor={identifierConfig.id}
            className={identifierError ? 'text-red-500' : ''}
          >
            {identifierConfig.label}
          </Label>
          <Input
            id={identifierConfig.id}
            type={identifierConfig.inputType}
            placeholder={identifierConfig.placeholder}
            value={identifier}
            onChange={handleIdentifierChange}
            disabled={isLoading || (!isPhone && showCodeInput && countdown > 0)}
            autoComplete={identifierConfig.autoComplete}
            className={cn(
              'text-base sm:text-sm',
              identifierError &&
                'border-red-500 focus-visible:ring-red-500 placeholder:text-muted-foreground',
            )}
          />
          {identifierError && (
            <p className='text-xs text-red-500'>{identifierError}</p>
          )}
        </div>

        {isPhone && (
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
              resetCaptchaChallenge({ clearError: true });
            }}
          />
        )}

        <div className='space-y-2'>
          <Label htmlFor={codeInputId}>
            {t('module.auth.verificationCode')}
          </Label>
          <div className='flex space-x-2'>
            <div className='flex-1'>
              <Input
                id={codeInputId}
                type='text'
                placeholder={t('module.auth.verificationCodePlaceholder')}
                value={verificationCode}
                onChange={event =>
                  setVerificationCode(
                    normalizeVerificationCode(event.target.value),
                  )
                }
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
              disabled={
                isLoading ||
                (isPhone && isCaptchaLoading) ||
                countdown > 0 ||
                !identifier ||
                !!identifierError ||
                (isPhone && !captchaCode.trim())
              }
              className='h-8 min-w-[100px] px-2 whitespace-nowrap'
            >
              {isLoading && !showCodeInput ? (
                <Loader2 className='h-4 w-4 animate-spin mr-2' />
              ) : countdown > 0 ? (
                t('module.auth.secondsLater', { count: countdown })
              ) : (
                t('module.auth.sendVerificationCode')
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
            disabled={isLoading || (!isPhone && !verificationCode)}
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
