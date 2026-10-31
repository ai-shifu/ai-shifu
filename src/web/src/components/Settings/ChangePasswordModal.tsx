'use client';

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { useToast } from '@/hooks/useToast';
import { useTracking } from '@/hooks/useTracking';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { DialogDescription, DialogTitle } from '@/components/ui/Dialog';
import {
  buildInstallationExposure,
  buildInstallationResult,
  INSTALLATION_AUTH_ATTEMPT,
  INSTALLATION_AUTH_EXPOSURE,
  INSTALLATION_AUTH_RESULT,
} from '@/components/installation/installationAnalytics';
import { isSecureInstallationOrigin } from '@/components/installation/installationRouting';
import SettingBaseModal from './SettingBaseModal';
import styles from './SettingBaseModal.module.scss';

export default function ChangePasswordModal({
  open,
  onClose,
  onSuccess,
}: {
  open: boolean;
  onClose: () => void;
  onSuccess?: () => void | Promise<void>;
}) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { trackEvent } = useTracking();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const exposed = useRef(false);
  const secure =
    typeof window !== 'undefined' &&
    isSecureInstallationOrigin(window.location);
  const emit = (event: string, data: Record<string, string>) => {
    try {
      void Promise.resolve(trackEvent(event, data)).catch(() => {});
    } catch {}
  };

  useEffect(() => {
    setCurrentPassword('');
    setNewPassword('');
    setConfirmation('');
    setErrorMessage('');
    if (!open) {
      exposed.current = false;
      return;
    }
    if (secure && !exposed.current) {
      exposed.current = true;
      try {
        void Promise.resolve(
          trackEvent(
            INSTALLATION_AUTH_EXPOSURE,
            buildInstallationExposure('local_password_change'),
          ),
        ).catch(() => {});
      } catch {}
    }
  }, [open, secure, trackEvent]);

  const submit = async () => {
    if (submitting.current || !secure) return;
    setErrorMessage('');
    if (!currentPassword || !newPassword || !confirmation) {
      setErrorMessage(t('module.installation.validationRequired'));
      return;
    }
    if (
      new Blob([currentPassword]).size > 72 ||
      new Blob([newPassword]).size > 72
    ) {
      setErrorMessage(t('server.installation.passwordTooLong'));
      return;
    }
    if (
      Array.from(newPassword).length < 8 ||
      !/[a-zA-Z]/.test(newPassword) ||
      !/[0-9]/.test(newPassword)
    ) {
      setErrorMessage(t('module.installation.passwordInvalid'));
      return;
    }
    if (newPassword !== confirmation) {
      setErrorMessage(t('module.installation.passwordMismatch'));
      return;
    }
    const payload = {
      old_password: currentPassword,
      new_password: newPassword,
    };
    submitting.current = true;
    setBusy(true);
    setCurrentPassword('');
    setNewPassword('');
    setConfirmation('');
    emit(
      INSTALLATION_AUTH_ATTEMPT,
      buildInstallationExposure('local_password_change'),
    );
    let succeeded = false;
    try {
      await api.changePassword(payload);
      succeeded = true;
      emit(
        INSTALLATION_AUTH_RESULT,
        buildInstallationResult('local_password_change', 'success', 'none'),
      );
    } catch (error) {
      const code =
        error && typeof error === 'object'
          ? (error as { code?: unknown }).code
          : undefined;
      setErrorMessage(t('module.installation.requestFailed'));
      emit(
        INSTALLATION_AUTH_RESULT,
        buildInstallationResult(
          'local_password_change',
          'failed',
          typeof code === 'number'
            ? 'credentials_rejected'
            : 'transport_or_service',
        ),
      );
    } finally {
      submitting.current = false;
      setBusy(false);
    }
    if (succeeded) {
      toast({ title: t('module.settings.passwordSetSuccess') });
      onClose();
      try {
        void Promise.resolve(onSuccess?.()).catch(() => {});
      } catch {}
    }
  };

  return (
    <SettingBaseModal
      open={open}
      onClose={() => {
        if (!submitting.current) onClose();
      }}
      onOk={() => void submit()}
      title={t('module.installation.changePassword')}
      header={(_, title) => (
        <DialogTitle asChild>
          <div className={styles.header}>{title}</div>
        </DialogTitle>
      )}
      okText={t('module.installation.changePassword')}
      okDisabled={
        !secure || busy || !currentPassword || !newPassword || !confirmation
      }
      okLoading={busy}
    >
      <DialogDescription className='sr-only'>
        {t('module.installation.passwordHelp')}
      </DialogDescription>
      {!secure ? (
        <p role='alert'>{t('module.installation.secureTransportRequired')}</p>
      ) : (
        <form
          className='space-y-4'
          onKeyDown={event => {
            if (
              event.key === 'Enter' &&
              event.target instanceof HTMLInputElement
            ) {
              event.preventDefault();
              void submit();
            }
          }}
          onSubmit={event => {
            event.preventDefault();
            void submit();
          }}
        >
          <div className='space-y-2'>
            <Label htmlFor='local-current-password'>
              {t('module.installation.currentPassword')}
            </Label>
            <Input
              id='local-current-password'
              type='password'
              autoComplete='current-password'
              value={currentPassword}
              onChange={event => setCurrentPassword(event.target.value)}
              disabled={busy}
            />
          </div>
          <div className='space-y-2'>
            <Label htmlFor='local-new-password'>
              {t('module.settings.newPassword')}
            </Label>
            <Input
              id='local-new-password'
              type='password'
              autoComplete='new-password'
              value={newPassword}
              onChange={event => setNewPassword(event.target.value)}
              disabled={busy}
              aria-describedby='local-password-help'
            />
            <p
              id='local-password-help'
              className='text-sm text-muted-foreground'
            >
              {t('module.installation.passwordHelp')}
            </p>
          </div>
          <div className='space-y-2'>
            <Label htmlFor='local-confirm-password'>
              {t('module.settings.confirmPassword')}
            </Label>
            <Input
              id='local-confirm-password'
              type='password'
              autoComplete='new-password'
              value={confirmation}
              onChange={event => setConfirmation(event.target.value)}
              disabled={busy}
            />
          </div>
          {errorMessage ? <p role='alert'>{errorMessage}</p> : null}
        </form>
      )}
    </SettingBaseModal>
  );
}
