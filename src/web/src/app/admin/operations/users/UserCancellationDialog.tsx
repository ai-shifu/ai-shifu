'use client';

import { useEffect, useState } from 'react';
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
import { ErrorWithCode } from '@/lib/request';
import { useTracking } from '@/hooks/useTracking';
import type {
  AdminOperationUserCancellationPreview,
  AdminOperationUserItem,
} from '../operation-user-types';

type Props = {
  open: boolean;
  user: AdminOperationUserItem | null;
  onOpenChange: (open: boolean) => void;
  onCancelled: () => void;
};

const cancellationBid = () => {
  if (typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID().replaceAll('-', '');
  }
  return `${Date.now()}${Math.random().toString(16).slice(2)}`;
};

const SUBSCRIPTION_BLOCKER = 'subscription_cancellation_required';

export default function UserCancellationDialog({
  open,
  user,
  onOpenChange,
  onCancelled,
}: Props) {
  const { t } = useTranslation('module.operationsUser');
  const { trackEvent } = useTracking();
  const [preview, setPreview] =
    useState<AdminOperationUserCancellationPreview | null>(null);
  const [reason, setReason] = useState('');
  const [contactType, setContactType] = useState<'phone' | 'email'>('phone');
  const [identifier, setIdentifier] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState('');

  const trackCancellationEvent = (
    eventName:
      | 'operator_user_cancellation_opened'
      | 'operator_user_cancellation_attempt'
      | 'operator_user_cancellation_result',
    properties: { surface: 'user_list'; outcome?: 'success' | 'failed' },
  ) => {
    try {
      void Promise.resolve(trackEvent(eventName, properties)).catch(() => {});
    } catch {
      // Analytics is best-effort and must never block account cancellation.
    }
  };

  const loadPreview = async () => {
    if (!user) return;
    setBusy(true);
    setError('');
    try {
      setPreview(
        (await api.getAdminOperationUserCancellationPreview({
          user_bid: user.user_bid,
        })) as AdminOperationUserCancellationPreview,
      );
    } catch (value) {
      setError(
        (value as ErrorWithCode).message || t('cancellation.errors.load'),
      );
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!open) return;
    setReason('');
    setIdentifier('');
    setConfirming(false);
    setPreview(null);
    void loadPreview();
    trackCancellationEvent('operator_user_cancellation_opened', {
      surface: 'user_list',
    });
    // Opening for another user remounts the workflow state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, user?.user_bid]);

  const transfer = async () => {
    if (!user || !identifier.trim()) return;
    setBusy(true);
    setError('');
    try {
      await api.transferAdminOperationUserPublishedCourses({
        user_bid: user.user_bid,
        contact_type: contactType,
        identifier: identifier.trim(),
      });
      await loadPreview();
    } catch (value) {
      setError(
        (value as ErrorWithCode).message || t('cancellation.errors.transfer'),
      );
      setBusy(false);
    }
  };

  const prepare = async () => {
    if (!user || !preview || reason.trim().length < 5) return;
    setBusy(true);
    setError('');
    try {
      let preparedPreview = preview;
      if (preparedPreview.subscription_renewal_count > 0) {
        const result = (await api.cancelAdminOperationUserSubscriptionRenewals({
          user_bid: user.user_bid,
        })) as { preview: AdminOperationUserCancellationPreview };
        preparedPreview = result.preview;
        setPreview(preparedPreview);
      }
      if (!preparedPreview.can_cancel) {
        setError(t('cancellation.errors.blocked'));
        return;
      }
      setConfirming(true);
    } catch (value) {
      setError(
        (value as ErrorWithCode).message || t('cancellation.errors.prepare'),
      );
    } finally {
      setBusy(false);
    }
  };

  const cancelAccount = async () => {
    if (!user || !preview) return;
    setBusy(true);
    const caseBid = cancellationBid();
    trackCancellationEvent('operator_user_cancellation_attempt', {
      surface: 'user_list',
    });
    try {
      await api.cancelAdminOperationUser({
        user_bid: user.user_bid,
        cancellation_bid: caseBid,
        preview_version: preview.preview_version,
        reason: reason.trim(),
      });
      trackCancellationEvent('operator_user_cancellation_result', {
        surface: 'user_list',
        outcome: 'success',
      });
      onOpenChange(false);
      onCancelled();
    } catch (value) {
      trackCancellationEvent('operator_user_cancellation_result', {
        surface: 'user_list',
        outcome: 'failed',
      });
      setConfirming(false);
      setError(
        (value as ErrorWithCode).message || t('cancellation.errors.cancel'),
      );
    } finally {
      setBusy(false);
    }
  };

  const hasManualBlocker = Boolean(
    preview?.blockers.some(blocker => blocker.code !== SUBSCRIPTION_BLOCKER),
  );
  const cannotContinue =
    busy ||
    !preview ||
    (!confirming && (hasManualBlocker || reason.trim().length < 5));

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className='sm:max-w-xl'>
        <DialogHeader>
          <DialogTitle>
            {confirming
              ? t('cancellation.confirmTitle')
              : t('cancellation.title')}
          </DialogTitle>
          <DialogDescription>
            {confirming
              ? t('cancellation.confirmDescription', {
                  user: preview?.user.masked_identifier || user?.user_bid,
                })
              : t('cancellation.description')}
          </DialogDescription>
        </DialogHeader>
        {error ? <p className='text-sm text-destructive'>{error}</p> : null}
        {!confirming ? (
          <div className='space-y-4'>
            {preview?.published_courses.length ? (
              <div className='space-y-2 rounded-lg border p-3'>
                <p className='text-sm'>
                  {t('cancellation.transferRequired', {
                    count: preview.published_courses.length,
                  })}
                </p>
                <div className='flex gap-2'>
                  <select
                    className='rounded-md border px-2 text-sm'
                    value={contactType}
                    onChange={event =>
                      setContactType(event.target.value as 'phone' | 'email')
                    }
                  >
                    <option value='phone'>
                      {t('loginMethodLabels.phone')}
                    </option>
                    <option value='email'>
                      {t('loginMethodLabels.email')}
                    </option>
                  </select>
                  <Input
                    value={identifier}
                    onChange={event => setIdentifier(event.target.value)}
                    placeholder={t('cancellation.transferPlaceholder')}
                  />
                  <Button
                    type='button'
                    onClick={transfer}
                    disabled={busy || !identifier.trim()}
                  >
                    {t('cancellation.transfer')}
                  </Button>
                </div>
              </div>
            ) : null}
            {preview ? (
              <ul className='space-y-1 text-sm text-muted-foreground'>
                <li>
                  {t('cancellation.summary.target', {
                    user:
                      preview.user.nickname || preview.user.masked_identifier,
                    identifier: preview.user.masked_identifier,
                  })}
                </li>
                <li>
                  {t('cancellation.summary.drafts', {
                    count: preview.draft_course_count,
                  })}
                </li>
                <li>
                  {t('cancellation.summary.credits', {
                    count: preview.available_credits,
                  })}
                </li>
                <li>
                  {t('cancellation.summary.sessions', {
                    count: preview.active_session_count,
                  })}
                </li>
                {preview.subscription_renewal_count > 0 ? (
                  <li>
                    {t('cancellation.summary.renewals', {
                      count: preview.subscription_renewal_count,
                    })}
                  </li>
                ) : null}
              </ul>
            ) : null}
            <Textarea
              value={reason}
              maxLength={500}
              onChange={event => setReason(event.target.value)}
              placeholder={t('cancellation.reasonPlaceholder')}
            />
          </div>
        ) : (
          <p className='rounded-lg bg-muted p-3 text-sm'>
            {t('cancellation.irreversible')}
          </p>
        )}
        <DialogFooter>
          <Button
            variant='outline'
            onClick={() =>
              confirming ? setConfirming(false) : onOpenChange(false)
            }
            disabled={busy}
          >
            {t('cancellation.back')}
          </Button>
          <Button
            variant='destructive'
            disabled={cannotContinue}
            onClick={confirming ? cancelAccount : prepare}
          >
            {confirming
              ? t('cancellation.confirm')
              : t('cancellation.continue')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
