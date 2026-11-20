'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import { useToast } from '@/hooks/use-toast';
import { useTracking } from '@/hooks/use-tracking';
import { ErrorWithCode } from '@/lib/request';
import type {
  AdminOperationUserCreateRequest,
  AdminOperationUserCreateResponse,
} from '../operation-user-types';

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (result: AdminOperationUserCreateResponse) => void;
};

type CreateFailureCategory = 'username_taken' | 'invalid_input' | 'other';

// Mirrors the backend contract in flaskr/service/user/usernames.py and
// password_utils.validate_password_strength; the backend stays authoritative.
const USERNAME_PATTERN = /^[a-z][a-z0-9_.-]{2,31}$/;
const NICKNAME_MAX_LENGTH = 50;
const USERNAME_TAKEN_CODE = 1047;
const INVALID_INPUT_CODES = new Set([1018, 1019, 1020, 1046, 1049]);

const isValidPassword = (value: string) =>
  value.length >= 8 && /[a-zA-Z]/.test(value) && /[0-9]/.test(value);

const resolveFailureCategory = (code?: number): CreateFailureCategory => {
  if (code === USERNAME_TAKEN_CODE) return 'username_taken';
  if (code !== undefined && INVALID_INPUT_CODES.has(code)) {
    return 'invalid_input';
  }
  return 'other';
};

export default function UserCreateAccountDialog({
  open,
  onOpenChange,
  onCreated,
}: Props) {
  const { t } = useTranslation('module.operationsUser');
  const { toast } = useToast();
  const { trackEvent } = useTracking();
  const [username, setUsername] = useState('');
  const [nickname, setNickname] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const submittedRef = useRef(false);

  const track = useCallback(
    (
      eventName:
        | 'operator_user_create_dialog_viewed'
        | 'operator_user_create_submitted'
        | 'operator_user_create_result',
      properties: Record<string, string> = {},
    ) => {
      try {
        void Promise.resolve(trackEvent(eventName, properties)).catch(() => {});
      } catch {
        // Analytics is best-effort and must never block account creation.
      }
    },
    [trackEvent],
  );

  useEffect(() => {
    if (!open) return;
    setUsername('');
    setNickname('');
    setPassword('');
    setConfirmPassword('');
    setError('');
    submittedRef.current = false;
    track('operator_user_create_dialog_viewed');
  }, [open, track]);

  const normalizedUsername = username.trim().toLowerCase();

  const validate = (): string => {
    if (!USERNAME_PATTERN.test(normalizedUsername)) {
      return t('createAccount.errors.usernameInvalid');
    }
    if (nickname.trim().length > NICKNAME_MAX_LENGTH) {
      return t('createAccount.errors.nicknameTooLong');
    }
    if (!isValidPassword(password)) {
      return t('createAccount.errors.passwordInvalid');
    }
    if (password !== confirmPassword) {
      return t('createAccount.errors.passwordMismatch');
    }
    return '';
  };

  const submit = async () => {
    if (submittedRef.current || submitting) return;
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }
    submittedRef.current = true;
    setSubmitting(true);
    setError('');
    track('operator_user_create_submitted');
    try {
      const payload: AdminOperationUserCreateRequest = {
        username: normalizedUsername,
        password,
        nickname: nickname.trim(),
      };
      const result = (await api.createAdminOperationUser(
        payload,
      )) as AdminOperationUserCreateResponse;
      track('operator_user_create_result', { result: 'success' });
      toast({
        title: t('createAccount.successTitle'),
        description: t('createAccount.successDescription', {
          username: result.username,
        }),
      });
      onCreated(result);
      onOpenChange(false);
    } catch (requestError) {
      submittedRef.current = false;
      const resolvedError = requestError as ErrorWithCode;
      setError(resolvedError.message || t('createAccount.errors.submitFailed'));
      track('operator_user_create_result', {
        result: 'failed',
        failure_category: resolveFailureCategory(resolvedError.code),
      });
    } finally {
      setSubmitting(false);
    }
  };

  const fields = [
    {
      id: 'operator-create-username',
      label: t('createAccount.usernameLabel'),
      placeholder: t('createAccount.usernamePlaceholder'),
      value: username,
      onChange: setUsername,
      type: 'text',
      autoComplete: 'off',
    },
    {
      id: 'operator-create-nickname',
      label: t('createAccount.nicknameLabel'),
      placeholder: t('createAccount.nicknamePlaceholder'),
      value: nickname,
      onChange: setNickname,
      type: 'text',
      autoComplete: 'off',
    },
    {
      id: 'operator-create-password',
      label: t('createAccount.passwordLabel'),
      placeholder: t('createAccount.passwordPlaceholder'),
      value: password,
      onChange: setPassword,
      type: 'password',
      autoComplete: 'new-password',
    },
    {
      id: 'operator-create-confirm-password',
      label: t('createAccount.confirmPasswordLabel'),
      placeholder: t('createAccount.confirmPasswordPlaceholder'),
      value: confirmPassword,
      onChange: setConfirmPassword,
      type: 'password',
      autoComplete: 'new-password',
    },
  ];

  return (
    <Dialog
      open={open}
      onOpenChange={nextOpen => {
        if (!submitting) onOpenChange(nextOpen);
      }}
    >
      <DialogContent
        onEscapeKeyDown={event => {
          if (submitting) event.preventDefault();
        }}
        onInteractOutside={event => {
          if (submitting) event.preventDefault();
        }}
      >
        <DialogHeader>
          <DialogTitle>{t('createAccount.title')}</DialogTitle>
          <DialogDescription>
            {t('createAccount.description')}
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-4 py-2'>
          {fields.map(field => (
            <div
              key={field.id}
              className='space-y-2'
            >
              <label
                htmlFor={field.id}
                className='text-sm font-medium'
              >
                {field.label}
              </label>
              <Input
                id={field.id}
                type={field.type}
                data-bidi='ltr'
                autoComplete={field.autoComplete}
                autoCapitalize='none'
                value={field.value}
                disabled={submitting}
                placeholder={field.placeholder}
                onChange={event => {
                  field.onChange(event.target.value);
                  setError('');
                }}
                onKeyDown={event => {
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    void submit();
                  }
                }}
              />
            </div>
          ))}
          {error ? (
            <p
              role='alert'
              className='text-sm text-destructive'
            >
              {error}
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <Button
            type='button'
            variant='outline'
            disabled={submitting}
            onClick={() => onOpenChange(false)}
          >
            {t('createAccount.cancel')}
          </Button>
          <Button
            type='button'
            disabled={submitting}
            onClick={() => void submit()}
          >
            {submitting
              ? t('createAccount.submitting')
              : t('createAccount.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
