import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import SettingBaseModal from './SettingBaseModal';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { useToast } from '@/hooks/use-toast';
import { EVENT_NAMES, useTracking } from '@/hooks/use-tracking';
import apiService from '@/api';
import { cn } from '@/lib/utils';

/**
 * Replace an existing password by confirming the current one.
 *
 * Unlike SetPasswordModal this needs no phone or email, so it also serves
 * username-only accounts whose first password was issued by an operator.
 */
export const ChangePasswordModal = ({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) => {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { trackEvent } = useTracking();

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [currentError, setCurrentError] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [confirmError, setConfirmError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const submittingRef = useRef(false);

  useEffect(() => {
    if (!open) return;
    setCurrentPassword('');
    setNewPassword('');
    setConfirmPassword('');
    setCurrentError('');
    setPasswordError('');
    setConfirmError('');
  }, [open]);

  const trackResult = useCallback(
    (result: 'success' | 'failed') => {
      try {
        void Promise.resolve(
          trackEvent(EVENT_NAMES.USER_PASSWORD_CHANGE_RESULT, { result }),
        ).catch(() => {});
      } catch {
        // Analytics is best-effort and must never block the password change.
      }
    },
    [trackEvent],
  );

  const validatePassword = useCallback(
    (value: string) => {
      let error = '';
      if (!value) error = t('module.auth.passwordEmpty');
      else if (value.length < 8) error = t('module.auth.passwordTooShort');
      else if (!/[a-zA-Z]/.test(value))
        error = t('module.auth.passwordNeedsLetter');
      else if (!/[0-9]/.test(value))
        error = t('module.auth.passwordNeedsDigit');
      setPasswordError(error);
      return !error;
    },
    [t],
  );

  const validateConfirm = useCallback(
    (password: string, value: string) => {
      let error = '';
      if (!value) error = t('module.settings.confirmPasswordEmpty');
      else if (password !== value)
        error = t('module.settings.passwordMismatch');
      setConfirmError(error);
      return !error;
    },
    [t],
  );

  const handleSubmit = useCallback(async () => {
    if (submittingRef.current) return;
    const okCurrent = Boolean(currentPassword);
    setCurrentError(okCurrent ? '' : t('module.settings.currentPasswordEmpty'));
    const okPassword = validatePassword(newPassword);
    const okConfirm = validateConfirm(newPassword, confirmPassword);
    if (!okCurrent || !okPassword || !okConfirm) return;

    submittingRef.current = true;
    setIsSubmitting(true);
    try {
      await apiService.changePassword({
        old_password: currentPassword,
        new_password: newPassword,
      });
      trackResult('success');
      toast({ title: t('module.settings.passwordChangeSuccess') });
      onClose();
    } catch {
      // The request wrapper shows the localized error, e.g. a wrong password.
      trackResult('failed');
    } finally {
      submittingRef.current = false;
      setIsSubmitting(false);
    }
  }, [
    confirmPassword,
    currentPassword,
    newPassword,
    onClose,
    t,
    toast,
    trackResult,
    validateConfirm,
    validatePassword,
  ]);

  const fields = [
    {
      id: 'change-password-current',
      label: t('module.settings.currentPassword'),
      value: currentPassword,
      error: currentError,
      autoComplete: 'current-password',
      onChange: (value: string) => {
        setCurrentPassword(value);
        if (currentError && value) setCurrentError('');
      },
    },
    {
      id: 'change-password-new',
      label: t('module.settings.newPassword'),
      value: newPassword,
      error: passwordError,
      autoComplete: 'new-password',
      onChange: (value: string) => {
        setNewPassword(value);
        if (passwordError) validatePassword(value);
        if (confirmPassword) validateConfirm(value, confirmPassword);
      },
    },
    {
      id: 'change-password-confirm',
      label: t('module.settings.confirmPassword'),
      value: confirmPassword,
      error: confirmError,
      autoComplete: 'new-password',
      onChange: (value: string) => {
        setConfirmPassword(value);
        if (confirmError) validateConfirm(newPassword, value);
      },
    },
  ];

  return (
    <SettingBaseModal
      open={open}
      onClose={onClose}
      onOk={handleSubmit}
      title={t('module.settings.changePassword')}
      okText={t('module.settings.changePassword')}
      okDisabled={
        isSubmitting || !currentPassword || !newPassword || !confirmPassword
      }
      okLoading={isSubmitting}
    >
      <div className='space-y-4'>
        {fields.map(field => (
          <div
            key={field.id}
            className='space-y-2'
          >
            <Label htmlFor={field.id}>{field.label}</Label>
            <Input
              id={field.id}
              type='password'
              data-bidi='ltr'
              value={field.value}
              onChange={event => field.onChange(event.target.value)}
              autoComplete={field.autoComplete}
              className={cn(field.error && 'border-destructive')}
              disabled={isSubmitting}
            />
            {field.error ? (
              <p className='text-sm text-destructive'>{field.error}</p>
            ) : null}
          </div>
        ))}
      </div>
    </SettingBaseModal>
  );
};

export default ChangePasswordModal;
