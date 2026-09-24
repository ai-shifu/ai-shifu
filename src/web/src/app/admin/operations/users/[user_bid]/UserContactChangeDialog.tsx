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
import { Textarea } from '@/components/ui/Textarea';
import { useToast } from '@/hooks/useToast';
import { useTracking } from '@/hooks/useTracking';
import { ErrorWithCode } from '@/lib/request';
import type {
  AdminOperationUserContactChangeRequest,
  AdminOperationUserContactChangeResponse,
} from '../../operation-user-types';

type Props = {
  open: boolean;
  userBid: string;
  contactType: 'phone' | 'email';
  currentIdentifier: string;
  onOpenChange: (open: boolean) => void;
  onChanged: (result: AdminOperationUserContactChangeResponse) => void;
};

const PHONE_PATTERN = /^\d{11}$/;
const EMAIL_PATTERN = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;

export default function UserContactChangeDialog({
  open,
  userBid,
  contactType,
  currentIdentifier,
  onOpenChange,
  onChanged,
}: Props) {
  const { t } = useTranslation('module.operationsUser');
  const { toast } = useToast();
  const { trackEvent } = useTracking();
  const [identifier, setIdentifier] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const submittedRef = useRef(false);

  const trackContactChange = useCallback(
    (
      eventName:
        | 'operator_user_contact_change_dialog_viewed'
        | 'operator_user_contact_change_submitted'
        | 'operator_user_contact_change_result',
      properties: {
        contact_type: 'phone' | 'email';
        result?: 'success' | 'failed';
      },
    ) => {
      try {
        void Promise.resolve(trackEvent(eventName, properties)).catch(() => {});
      } catch {
        // Analytics is best-effort and must never block the contact change.
      }
    },
    [trackEvent],
  );

  useEffect(() => {
    if (!open) return;
    setIdentifier('');
    setConfirmation('');
    setReason('');
    setError('');
    submittedRef.current = false;
    trackContactChange('operator_user_contact_change_dialog_viewed', {
      contact_type: contactType,
    });
  }, [contactType, open, trackContactChange]);

  const normalizedIdentifier =
    contactType === 'email'
      ? identifier.trim().toLowerCase()
      : identifier.trim();
  const normalizedConfirmation =
    contactType === 'email'
      ? confirmation.trim().toLowerCase()
      : confirmation.trim();

  const validate = (): string => {
    if (!normalizedIdentifier) {
      return t(`contactChange.errors.${contactType}Required`);
    }
    if (
      (contactType === 'phone' && !PHONE_PATTERN.test(normalizedIdentifier)) ||
      (contactType === 'email' && !EMAIL_PATTERN.test(normalizedIdentifier))
    ) {
      return t(`contactChange.errors.${contactType}Invalid`);
    }
    if (normalizedIdentifier === currentIdentifier.trim().toLowerCase()) {
      return t(`contactChange.errors.${contactType}Unchanged`);
    }
    if (normalizedConfirmation !== normalizedIdentifier) {
      return t('contactChange.errors.confirmationMismatch');
    }
    if (!reason.trim()) return t('contactChange.errors.reasonRequired');
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
    trackContactChange('operator_user_contact_change_submitted', {
      contact_type: contactType,
    });
    try {
      const payload: AdminOperationUserContactChangeRequest = {
        contact_type: contactType,
        identifier: normalizedIdentifier,
        reason: reason.trim(),
      };
      const result = (await api.changeAdminOperationUserContact({
        user_bid: userBid,
        ...payload,
      })) as AdminOperationUserContactChangeResponse;
      trackContactChange('operator_user_contact_change_result', {
        contact_type: contactType,
        result: 'success',
      });
      toast({
        title: t(`contactChange.${contactType}.successTitle`),
        description: t(`contactChange.${contactType}.successDescription`),
      });
      onChanged(result);
      onOpenChange(false);
    } catch (requestError) {
      submittedRef.current = false;
      const resolvedError = requestError as ErrorWithCode;
      setError(resolvedError.message || t('contactChange.errors.submitFailed'));
      trackContactChange('operator_user_contact_change_result', {
        contact_type: contactType,
        result: 'failed',
      });
    } finally {
      setSubmitting(false);
    }
  };

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
          <DialogTitle>{t(`contactChange.${contactType}.title`)}</DialogTitle>
          <DialogDescription>
            {t(`contactChange.${contactType}.description`)}
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-4 py-2'>
          <div className='space-y-2'>
            <label className='text-sm font-medium'>
              {t(`contactChange.${contactType}.currentLabel`)}
            </label>
            <div className='break-all text-sm text-muted-foreground'>
              {currentIdentifier || '--'}
            </div>
          </div>
          <div className='space-y-2'>
            <label
              htmlFor='operator-new-contact'
              className='text-sm font-medium'
            >
              {t(`contactChange.${contactType}.newLabel`)}
            </label>
            <Input
              id='operator-new-contact'
              value={identifier}
              disabled={submitting}
              placeholder={t(`contactChange.${contactType}.newPlaceholder`)}
              onChange={event => setIdentifier(event.target.value)}
            />
          </div>
          <div className='space-y-2'>
            <label
              htmlFor='operator-confirm-contact'
              className='text-sm font-medium'
            >
              {t(`contactChange.${contactType}.confirmLabel`)}
            </label>
            <Input
              id='operator-confirm-contact'
              value={confirmation}
              disabled={submitting}
              placeholder={t(`contactChange.${contactType}.confirmPlaceholder`)}
              onChange={event => setConfirmation(event.target.value)}
            />
          </div>
          <div className='space-y-2'>
            <label
              htmlFor='operator-contact-change-reason'
              className='text-sm font-medium'
            >
              {t('contactChange.reasonLabel')}
            </label>
            <Textarea
              id='operator-contact-change-reason'
              value={reason}
              disabled={submitting}
              maxLength={500}
              placeholder={t('contactChange.reasonPlaceholder')}
              onChange={event => setReason(event.target.value)}
            />
          </div>
          <p className='text-sm text-muted-foreground'>
            {t(`contactChange.${contactType}.sessionNotice`)}
          </p>
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
            {t('contactChange.cancel')}
          </Button>
          <Button
            type='button'
            disabled={submitting}
            onClick={() => void submit()}
          >
            {submitting
              ? t('contactChange.submitting')
              : t('contactChange.confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
