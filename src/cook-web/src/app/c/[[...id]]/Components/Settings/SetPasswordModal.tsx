import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import SettingBaseModal from './SettingBaseModal';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { useToast } from '@/hooks/useToast';
import apiService from '@/api';
import i18n from '@/i18n';
import { useUserStore } from '@/store';
import { cn } from '@/lib/utils';

type VerificationMethod = 'phone' | 'email';

export const SetPasswordModal = ({
  open,
  onClose,
  onSuccess,
}: {
  open: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}) => {
  const { t } = useTranslation();
  const { toast } = useToast();
  const userInfo = useUserStore(state => state.userInfo);

  const availableMethods = useMemo<VerificationMethod[]>(() => {
    const methods: VerificationMethod[] = [];
    if (userInfo?.mobile) methods.push('phone');
    if (userInfo?.email) methods.push('email');
    return methods;
  }, [userInfo?.email, userInfo?.mobile]);

  const [method, setMethod] = useState<VerificationMethod>('phone');

  useEffect(() => {
    if (!open) {
      return;
    }
    if (availableMethods.length === 0) {
      return;
    }
    if (!availableMethods.includes(method)) {
      setMethod(availableMethods[0]);
    }
  }, [availableMethods, method, open]);

  const identifier =
    method === 'phone' ? userInfo?.mobile || '' : userInfo?.email || '';

  const [code, setCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [countdown, setCountdown] = useState(0);
  const [isSending, setIsSending] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [passwordError, setPasswordError] = useState('');
  const [confirmError, setConfirmError] = useState('');

  useEffect(() => {
    if (!open) {
      return;
    }
    setCode('');
    setNewPassword('');
    setConfirmPassword('');
    setCountdown(0);
    setIsSending(false);
    setIsSubmitting(false);
    setPasswordError('');
    setConfirmError('');
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    if (countdown <= 0) {
      return;
    }

    const timer = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          clearInterval(timer);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [countdown, open]);

  const validatePassword = useCallback(
    (value: string) => {
      if (!value) {
        setPasswordError(t('module.auth.passwordEmpty'));
        return false;
      }
      if (value.length < 8) {
        setPasswordError(t('module.auth.passwordTooShort'));
        return false;
      }
      if (!/[a-zA-Z]/.test(value)) {
        setPasswordError(t('module.auth.passwordNeedsLetter'));
        return false;
      }
      if (!/[0-9]/.test(value)) {
        setPasswordError(t('module.auth.passwordNeedsDigit'));
        return false;
      }
      setPasswordError('');
      return true;
    },
    [t],
  );

  const validateConfirmPassword = useCallback(
    (password: string, value: string) => {
      if (!value) {
        setConfirmError(t('module.settings.confirmPasswordEmpty'));
        return false;
      }
      if (password !== value) {
        setConfirmError(t('module.settings.passwordMismatch'));
        return false;
      }
      setConfirmError('');
      return true;
    },
    [t],
  );

  const handleSendCode = useCallback(async () => {
    if (!identifier) {
      toast({
        title: t('module.settings.noContactMethod'),
        variant: 'destructive',
      });
      return;
    }

    try {
      setIsSending(true);
      if (method === 'phone') {
        await apiService.sendSmsCode({
          mobile: identifier,
          language: i18n.language,
        });
      } else {
        await apiService.sendEmailCode({
          email: identifier,
          language: i18n.language,
        });
      }

      toast({
        title: t('module.auth.sendSuccess'),
        description: t('module.settings.codeSent'),
      });
      setCountdown(60);
    } catch {
      // Errors are handled by request wrapper
    } finally {
      setIsSending(false);
    }
  }, [identifier, method, t, toast]);

  const handleSubmit = useCallback(async () => {
    if (!identifier) {
      toast({
        title: t('module.settings.noContactMethod'),
        variant: 'destructive',
      });
      return;
    }

    if (!code) {
      toast({
        title: t('module.settings.verificationCodeRequired'),
        variant: 'destructive',
      });
      return;
    }

    const okPassword = validatePassword(newPassword);
    const okConfirm = validateConfirmPassword(newPassword, confirmPassword);
    if (!okPassword || !okConfirm) {
      return;
    }

    try {
      setIsSubmitting(true);
      await apiService.setPassword({
        identifier,
        code,
        new_password: newPassword,
      });

      toast({ title: t('module.settings.passwordSetSuccess') });
      onSuccess?.();
      onClose();
    } catch {
      // Errors are handled by request wrapper
    } finally {
      setIsSubmitting(false);
    }
  }, [
    code,
    confirmPassword,
    identifier,
    newPassword,
    onClose,
    onSuccess,
    t,
    toast,
    validateConfirmPassword,
    validatePassword,
  ]);

  const hasMultipleMethods = availableMethods.length > 1;
  const okDisabled =
    !identifier ||
    !code ||
    !newPassword ||
    !confirmPassword ||
    isSubmitting ||
    availableMethods.length === 0;

  return (
    <SettingBaseModal
      open={open}
      onClose={onClose}
      onOk={handleSubmit}
      title={t('module.settings.setPassword')}
      okText={t('module.settings.setPassword')}
      okDisabled={okDisabled}
      okLoading={isSubmitting}
    >
      <div className='space-y-4'>
        {availableMethods.length === 0 ? (
          <p className='text-sm text-muted-foreground'>
            {t('module.settings.noContactMethod')}
          </p>
        ) : null}

        {hasMultipleMethods ? (
          <div className='flex gap-2'>
            {availableMethods.includes('phone') ? (
              <Button
                type='button'
                variant={method === 'phone' ? 'default' : 'outline'}
                className='h-8 flex-1'
                onClick={() => setMethod('phone')}
                disabled={isSending || isSubmitting}
              >
                {t('module.settings.verifyByPhone')}
              </Button>
            ) : null}
            {availableMethods.includes('email') ? (
              <Button
                type='button'
                variant={method === 'email' ? 'default' : 'outline'}
                className='h-8 flex-1'
                onClick={() => setMethod('email')}
                disabled={isSending || isSubmitting}
              >
                {t('module.settings.verifyByEmail')}
              </Button>
            ) : null}
          </div>
        ) : null}

        <div className='space-y-2'>
          <Label className='text-muted-foreground'>
            {method === 'phone'
              ? t('module.auth.phone')
              : t('module.auth.email')}
          </Label>
          <Input
            value={identifier}
            disabled
            className='bg-muted text-base sm:text-sm'
          />
        </div>

        <div className='flex gap-2 items-end'>
          <div className='flex-1 space-y-2'>
            <Label className='text-muted-foreground'>
              {t('module.settings.verificationCode')}
            </Label>
            <Input
              value={code}
              onChange={e => setCode(e.target.value.trim())}
              placeholder={t('module.settings.verificationCodePlaceholder')}
              disabled={isSubmitting}
              inputMode='numeric'
              className='text-base sm:text-sm'
            />
          </div>
          <Button
            type='button'
            onClick={handleSendCode}
            className='h-8 whitespace-nowrap'
            disabled={
              isSending ||
              isSubmitting ||
              countdown > 0 ||
              !identifier ||
              availableMethods.length === 0
            }
          >
            {countdown > 0
              ? t('module.auth.secondsLater', { count: countdown })
              : t('module.settings.sendCode')}
          </Button>
        </div>

        <div className='space-y-2'>
          <Label
            className={passwordError ? 'text-red-500' : 'text-muted-foreground'}
          >
            {t('module.settings.newPassword')}
          </Label>
          <Input
            type='password'
            value={newPassword}
            onChange={e => {
              const value = e.target.value;
              setNewPassword(value);
              if (value) validatePassword(value);
              else setPasswordError('');
              if (confirmPassword) {
                validateConfirmPassword(value, confirmPassword);
              }
            }}
            placeholder={t('module.auth.passwordPlaceholder')}
            disabled={isSubmitting}
            className={cn(
              'text-base sm:text-sm',
              passwordError &&
                'border-red-500 focus-visible:ring-red-500 placeholder:text-muted-foreground',
            )}
          />
          {passwordError ? (
            <p className='text-xs text-red-500'>{passwordError}</p>
          ) : null}
        </div>

        <div className='space-y-2'>
          <Label
            className={confirmError ? 'text-red-500' : 'text-muted-foreground'}
          >
            {t('module.settings.confirmPassword')}
          </Label>
          <Input
            type='password'
            value={confirmPassword}
            onChange={e => {
              const value = e.target.value;
              setConfirmPassword(value);
              if (value) validateConfirmPassword(newPassword, value);
              else setConfirmError('');
            }}
            placeholder={t('module.settings.confirmPasswordPlaceholder')}
            disabled={isSubmitting}
            className={cn(
              'text-base sm:text-sm',
              confirmError &&
                'border-red-500 focus-visible:ring-red-500 placeholder:text-muted-foreground',
            )}
          />
          {confirmError ? (
            <p className='text-xs text-red-500'>{confirmError}</p>
          ) : null}
        </div>
      </div>
    </SettingBaseModal>
  );
};

export default SetPasswordModal;
