'use client';

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { v4 as uuidv4 } from 'uuid';
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
import { Textarea } from '@/components/ui/Textarea';
import { useToast } from '@/hooks/useToast';
import { useTracking } from '@/hooks/useTracking';
import { ErrorWithCode } from '@/lib/request';
import type {
  AdminOperationUserItem,
  AdminOperationUserSubscriptionTerminationResponse,
} from '../operation-user-types';

type Props = {
  open: boolean;
  user: AdminOperationUserItem | null;
  onOpenChange: (open: boolean) => void;
  onTerminated: (
    result: AdminOperationUserSubscriptionTerminationResponse,
  ) => void;
};

export default function UserSubscriptionTerminationDialog({
  open,
  user,
  onOpenChange,
  onTerminated,
}: Props) {
  const { t } = useTranslation('module.operationsUser');
  const { toast } = useToast();
  const { trackEvent } = useTracking();
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const requestIdRef = useRef('');
  const submittingRef = useRef(false);
  const account =
    user?.mobile?.trim() || user?.email?.trim() || user?.user_bid || '';

  useEffect(() => {
    if (!open || submittingRef.current) return;
    requestIdRef.current = uuidv4();
    setReason('');
    setError('');
    setSubmitting(false);
  }, [open, user?.user_bid]);

  const track = (outcome?: 'success' | 'failed') => {
    try {
      const name = outcome
        ? 'operator_subscription_termination_result'
        : 'operator_subscription_termination_attempt';
      const payload = outcome
        ? { surface: 'operator_user_management', outcome }
        : { surface: 'operator_user_management' };
      void Promise.resolve(trackEvent(name, payload)).catch(() => {});
    } catch {
      // Analytics must not affect subscription termination.
    }
  };

  const submit = async () => {
    const subscriptionBid = user?.termination_subscription_bid?.trim() || '';
    if (!user || !subscriptionBid || submittingRef.current) return;
    const normalizedReason = reason.trim();
    if (!normalizedReason) {
      setError(t('terminationDialog.errors.reason'));
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    setError('');
    track();
    try {
      const result = (await api.terminateAdminOperationUserSubscription({
        user_bid: user.user_bid,
        subscription_bid: subscriptionBid,
        request_id: requestIdRef.current,
        reason: normalizedReason,
      })) as AdminOperationUserSubscriptionTerminationResponse;
      track('success');
      toast({ title: t('terminationDialog.success') });
      submittingRef.current = false;
      setSubmitting(false);
      onTerminated(result);
    } catch (requestError) {
      track('failed');
      const resolved = requestError as ErrorWithCode;
      setError(resolved.message || t('terminationDialog.errors.submitFailed'));
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={nextOpen => {
        if (submittingRef.current) return;
        onOpenChange(nextOpen);
      }}
    >
      <DialogContent className='max-w-[560px]'>
        <DialogHeader>
          <DialogTitle>{t('terminationDialog.title')}</DialogTitle>
          <DialogDescription>
            {t('terminationDialog.description')}
          </DialogDescription>
        </DialogHeader>
        <div className='space-y-4 py-2'>
          <div className='rounded-md border border-border p-4 text-sm'>
            <div className='flex justify-between gap-4'>
              <span className='text-muted-foreground'>
                {t('terminationDialog.account')}
              </span>
              <span className='break-all text-right'>{account}</span>
            </div>
            <div className='mt-3 flex justify-between gap-4'>
              <span className='text-muted-foreground'>
                {t('terminationDialog.subscriptionId')}
              </span>
              <span className='break-all text-right'>
                {user?.termination_subscription_bid || ''}
              </span>
            </div>
          </div>
          <div>
            <label
              className='mb-2 block text-sm font-medium'
              htmlFor='termination-reason'
            >
              {t('terminationDialog.reason')}
            </label>
            <Textarea
              id='termination-reason'
              value={reason}
              maxLength={255}
              disabled={submitting}
              placeholder={t('terminationDialog.reasonPlaceholder')}
              onChange={event => setReason(event.target.value)}
            />
          </div>
          {error ? <p className='text-sm text-destructive'>{error}</p> : null}
        </div>
        <DialogFooter>
          <Button
            variant='outline'
            disabled={submitting}
            onClick={() => onOpenChange(false)}
          >
            {t('terminationDialog.cancel')}
          </Button>
          <Button
            disabled={submitting || !user?.termination_subscription_bid}
            onClick={() => void submit()}
          >
            {t(
              submitting
                ? 'terminationDialog.submitting'
                : 'terminationDialog.confirm',
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
