'use client';

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CircleHelp } from 'lucide-react';
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
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { ErrorWithCode } from '@/lib/request';
import { getTrackingIdentityGeneration } from '@/lib/tracking';
import { useTracking } from '@/hooks/useTracking';
import type {
  AdminOperationUserCancellationPreview,
  AdminOperationUserCancellationStatus,
  AdminOperationUserItem,
} from '../operation-user-types';
import { formatOperatorUtcDateTime } from './dateTime';

type Props = {
  open: boolean;
  user: AdminOperationUserItem | null;
  contactType: 'phone' | 'email';
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
const CANCELLATION_POLL_INTERVAL_MS = 500;
const CANCELLATION_POLL_LIMIT = 120;
const CANCELLATION_PREVIEW_STALE_CODE = 1037;
const CANCELLATION_BLOCKED_CODE = 1035;

const waitForCancellation = async (
  userBid: string,
  caseBid: string,
  timeoutMessage: string,
  isCurrentWorkflow: () => boolean,
): Promise<AdminOperationUserCancellationStatus | null> => {
  for (let attempt = 0; attempt < CANCELLATION_POLL_LIMIT; attempt += 1) {
    if (!isCurrentWorkflow()) return null;
    const status = (await api.getAdminOperationUserCancellationStatus({
      user_bid: userBid,
      cancellation_bid: caseBid,
    })) as AdminOperationUserCancellationStatus;
    if (!isCurrentWorkflow()) return null;
    if (status.status === 'completed' || status.status === 'failed') {
      return status;
    }
    await new Promise(resolve =>
      window.setTimeout(resolve, CANCELLATION_POLL_INTERVAL_MS),
    );
  }
  throw new Error(timeoutMessage);
};

const BLOCKER_CODES = [
  'self',
  'operator',
  'published_course_transfer_required',
  'unsettled_payment',
] as const;

const SummaryLabel = ({
  label,
  tooltip,
}: {
  label: React.ReactNode;
  tooltip?: string;
}) => (
  <dt className='flex items-center gap-1 text-xs text-muted-foreground'>
    <span>{label}</span>
    {tooltip ? (
      <TooltipProvider delayDuration={0}>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type='button'
              aria-label={tooltip}
              className='inline-flex h-3 w-3 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:ring-offset-1'
            >
              <CircleHelp className='h-3 w-3' />
            </button>
          </TooltipTrigger>
          <TooltipContent className='z-[112] max-w-64 text-left text-xs leading-5'>
            {tooltip}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    ) : null}
  </dt>
);

const SummaryValue = ({ value }: { value: React.ReactNode }) => (
  <dd className='mt-1 break-all text-sm text-foreground'>{value}</dd>
);

const packageNames = (
  packages: AdminOperationUserCancellationPreview['paid_packages'],
  translate: (key: string) => string,
) =>
  packages
    .map(item =>
      item.product_name_i18n_key
        ? translate(item.product_name_i18n_key)
        : item.product_code || item.product_bid,
    )
    .join('、');

export default function UserCancellationDialog({
  open,
  user,
  contactType,
  onOpenChange,
  onCancelled,
}: Props) {
  const { t: tGlobal } = useTranslation();
  const { t } = useTranslation('module.operationsUser');
  const { trackEvent } = useTracking();
  const [preview, setPreview] =
    useState<AdminOperationUserCancellationPreview | null>(null);
  const [reason, setReason] = useState('');
  const [identifier, setIdentifier] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState('');
  const previewRequestRef = useRef(0);
  const workflowBidRef = useRef('');
  const openedWorkflowRef = useRef('');
  const workflowSequenceRef = useRef(0);
  const activeWorkflowRef = useRef<{ id: number; userBid: string } | null>(
    null,
  );

  const isCurrentWorkflow = (workflow: { id: number; userBid: string }) => {
    const active = activeWorkflowRef.current;
    return active?.id === workflow.id && active.userBid === workflow.userBid;
  };

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

  const loadPreview = async (
    requestedUser = user,
    workflow = activeWorkflowRef.current,
  ) => {
    if (!requestedUser) return null;
    if (!workflow || workflow.userBid !== requestedUser.user_bid) return null;
    const requestId = previewRequestRef.current + 1;
    previewRequestRef.current = requestId;
    setBusy(true);
    setError('');
    try {
      const result = (await api.getAdminOperationUserCancellationPreview({
        user_bid: requestedUser.user_bid,
      })) as AdminOperationUserCancellationPreview;
      if (
        previewRequestRef.current === requestId &&
        isCurrentWorkflow(workflow)
      ) {
        setPreview(result);
      }
      return result;
    } catch (value) {
      if (
        previewRequestRef.current === requestId &&
        isCurrentWorkflow(workflow)
      ) {
        setError(
          (value as ErrorWithCode).message || t('cancellation.errors.load'),
        );
      }
      return null;
    } finally {
      if (
        previewRequestRef.current === requestId &&
        isCurrentWorkflow(workflow)
      ) {
        setBusy(false);
      }
    }
  };

  useEffect(() => {
    if (!open) return;
    const workflow = {
      id: workflowSequenceRef.current + 1,
      userBid: user?.user_bid || '',
    };
    workflowSequenceRef.current = workflow.id;
    activeWorkflowRef.current = workflow;
    setReason('');
    setIdentifier('');
    setConfirming(false);
    setPreview(null);
    workflowBidRef.current = cancellationBid();
    void loadPreview(user, workflow);
    const workflowKey = `${user?.user_bid || ''}:${workflowBidRef.current}`;
    if (user && openedWorkflowRef.current !== workflowKey) {
      openedWorkflowRef.current = workflowKey;
      trackCancellationEvent('operator_user_cancellation_opened', {
        surface: 'user_list',
      });
    }
    return () => {
      previewRequestRef.current += 1;
      if (isCurrentWorkflow(workflow)) {
        activeWorkflowRef.current = null;
      }
    };
    // Opening for another user remounts the workflow state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, user?.user_bid]);

  const transfer = async () => {
    if (!user || preview?.user.user_bid !== user.user_bid || !identifier.trim())
      return;
    const workflow = activeWorkflowRef.current;
    if (!workflow || workflow.userBid !== user.user_bid) return;
    setBusy(true);
    setError('');
    try {
      await api.transferAdminOperationUserPublishedCourses({
        user_bid: user.user_bid,
        contact_type: contactType,
        identifier: identifier.trim(),
      });
      if (!isCurrentWorkflow(workflow)) return;
      await loadPreview(user, workflow);
    } catch (value) {
      if (!isCurrentWorkflow(workflow)) return;
      setError(
        (value as ErrorWithCode).message || t('cancellation.errors.transfer'),
      );
      setBusy(false);
    }
  };

  const prepare = async () => {
    if (
      !user ||
      !preview ||
      preview.user.user_bid !== user.user_bid ||
      reason.trim().length < 5
    )
      return;
    const workflow = activeWorkflowRef.current;
    if (!workflow || workflow.userBid !== user.user_bid) return;
    setBusy(true);
    setError('');
    try {
      let preparedPreview = preview;
      if (preparedPreview.subscription_renewal_count > 0) {
        const result = (await api.cancelAdminOperationUserSubscriptionRenewals({
          user_bid: user.user_bid,
        })) as { preview: AdminOperationUserCancellationPreview };
        if (!isCurrentWorkflow(workflow)) return;
        preparedPreview = result.preview;
        setPreview(preparedPreview);
      }
      if (!preparedPreview.can_cancel) {
        setError(t('cancellation.errors.blocked'));
        return;
      }
      if (!isCurrentWorkflow(workflow)) return;
      setConfirming(true);
    } catch (value) {
      if (!isCurrentWorkflow(workflow)) return;
      setError(
        (value as ErrorWithCode).message || t('cancellation.errors.prepare'),
      );
    } finally {
      if (isCurrentWorkflow(workflow)) setBusy(false);
    }
  };

  const cancelAccount = async () => {
    if (!user || !preview || preview.user.user_bid !== user.user_bid) return;
    const workflow = activeWorkflowRef.current;
    if (!workflow || workflow.userBid !== user.user_bid) return;
    const trackingIdentityGeneration = getTrackingIdentityGeneration();
    setBusy(true);
    const caseBid = workflowBidRef.current || cancellationBid();
    workflowBidRef.current = caseBid;
    trackCancellationEvent('operator_user_cancellation_attempt', {
      surface: 'user_list',
    });
    try {
      const accepted = (await api.cancelAdminOperationUser({
        user_bid: user.user_bid,
        cancellation_bid: caseBid,
        preview_version: preview.preview_version,
        reason: reason.trim(),
      })) as AdminOperationUserCancellationStatus;
      const result =
        accepted.status === 'completed'
          ? accepted
          : await waitForCancellation(
              user.user_bid,
              accepted.cancellation_bid,
              t('cancellation.errors.processingTimeout'),
              () => isCurrentWorkflow(workflow),
            );
      if (!result || !isCurrentWorkflow(workflow)) return;
      if (result.status !== 'completed') {
        throw new Error(t('cancellation.errors.executionFailed'));
      }
      if (getTrackingIdentityGeneration() === trackingIdentityGeneration) {
        trackCancellationEvent('operator_user_cancellation_result', {
          surface: 'user_list',
          outcome: 'success',
        });
      }
      activeWorkflowRef.current = null;
      onOpenChange(false);
      onCancelled();
      workflowBidRef.current = '';
    } catch (value) {
      if (!isCurrentWorkflow(workflow)) return;
      if (getTrackingIdentityGeneration() === trackingIdentityGeneration) {
        trackCancellationEvent('operator_user_cancellation_result', {
          surface: 'user_list',
          outcome: 'failed',
        });
      }
      setConfirming(false);
      const requestError = value as ErrorWithCode;
      if (
        requestError.code === CANCELLATION_PREVIEW_STALE_CODE ||
        requestError.code === CANCELLATION_BLOCKED_CODE
      ) {
        await loadPreview(user, workflow);
        if (isCurrentWorkflow(workflow)) {
          setError(requestError.message || t('cancellation.errors.blocked'));
        }
      } else {
        setError(requestError.message || t('cancellation.errors.cancel'));
      }
    } finally {
      if (isCurrentWorkflow(workflow)) setBusy(false);
    }
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      previewRequestRef.current += 1;
      activeWorkflowRef.current = null;
    }
    onOpenChange(nextOpen);
  };

  const hasManualBlocker = Boolean(
    preview?.blockers.some(blocker => blocker.code !== SUBSCRIPTION_BLOCKER),
  );
  const cannotContinue =
    busy ||
    !preview ||
    (!confirming && (hasManualBlocker || reason.trim().length < 5));
  const accountIdentifier =
    preview?.user.identifier ||
    user?.mobile ||
    user?.email ||
    preview?.user.masked_identifier ||
    user?.user_bid ||
    '--';
  const reasonLength = reason.trim().length;
  const creditsExpireAt = user?.credits_expire_at
    ? formatOperatorUtcDateTime(user.credits_expire_at)
    : Number(preview?.available_credits || 0) > 0
      ? t('credits.longTerm')
      : '--';

  return (
    <Dialog
      open={open}
      onOpenChange={handleOpenChange}
    >
      <DialogContent className='flex max-h-[85vh] w-[calc(100vw-32px)] flex-col gap-0 overflow-hidden p-0 sm:max-w-[560px]'>
        <DialogHeader className='px-5 pb-3 pt-5'>
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
        <div className='min-h-0 flex-1 overflow-y-auto px-5 py-4'>
          {error ? (
            <p className='mb-3 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive'>
              {error}
            </p>
          ) : null}
          {!confirming ? (
            <div className='space-y-4'>
              {preview ? (
                <div className='rounded-xl border border-border/70 bg-muted/[0.16] px-4 py-3'>
                  <dl className='grid gap-x-5 gap-y-3 sm:grid-cols-2'>
                    <div>
                      <SummaryLabel
                        label={t('cancellation.summary.accountLabel')}
                      />
                      <SummaryValue value={accountIdentifier} />
                    </div>
                    <div>
                      <SummaryLabel
                        label={t('cancellation.summary.coursesLabel')}
                        tooltip={t('cancellation.summary.coursesHint')}
                      />
                      <SummaryValue
                        value={t('cancellation.summary.courseCounts', {
                          drafts: preview.draft_course_count,
                          published: preview.published_courses.length,
                        })}
                      />
                    </div>
                    <div>
                      <SummaryLabel
                        label={t('cancellation.summary.creditsLabel')}
                        tooltip={t('cancellation.summary.creditsHint')}
                      />
                      <SummaryValue value={preview.available_credits} />
                    </div>
                    <div>
                      <SummaryLabel
                        label={t('cancellation.summary.creditsExpireAtLabel')}
                      />
                      <SummaryValue value={creditsExpireAt} />
                    </div>
                  </dl>
                  {preview.paid_packages?.length ||
                  preview.preorder_packages?.length ||
                  preview.renewing_packages?.length ? (
                    <dl className='mt-3 flex flex-wrap gap-x-6 gap-y-2 border-t border-border/60 pt-3 text-sm'>
                      {preview.paid_packages?.length ? (
                        <div className='flex gap-2'>
                          <dt className='shrink-0 text-muted-foreground'>
                            {t('cancellation.summary.paidPackages')}
                          </dt>
                          <dd className='break-all text-foreground'>
                            {packageNames(preview.paid_packages || [], key =>
                              tGlobal(key),
                            )}
                          </dd>
                        </div>
                      ) : null}
                      {preview.preorder_packages?.length ? (
                        <div className='flex gap-2'>
                          <dt className='shrink-0 text-muted-foreground'>
                            {t('cancellation.summary.preorders')}
                          </dt>
                          <dd className='break-all text-foreground'>
                            {packageNames(
                              preview.preorder_packages || [],
                              key => tGlobal(key),
                            )}
                          </dd>
                        </div>
                      ) : null}
                      {preview.renewing_packages?.length ? (
                        <div className='flex gap-2'>
                          <dt className='shrink-0 text-muted-foreground'>
                            {t('cancellation.summary.subscriptions')}
                          </dt>
                          <dd className='break-all text-foreground'>
                            {packageNames(
                              preview.renewing_packages || [],
                              key => tGlobal(key),
                            )}
                          </dd>
                        </div>
                      ) : null}
                    </dl>
                  ) : null}
                </div>
              ) : null}
              {preview?.blockers.some(
                blocker =>
                  blocker.code !== SUBSCRIPTION_BLOCKER &&
                  blocker.code !== 'published_course_transfer_required',
              ) ? (
                <div className='rounded-lg border border-amber-200 bg-amber-50/60 px-4 py-3'>
                  <ul className='list-disc space-y-1 pl-5 text-sm text-amber-800'>
                    {preview.blockers
                      .filter(
                        blocker =>
                          blocker.code !== SUBSCRIPTION_BLOCKER &&
                          blocker.code !== 'published_course_transfer_required',
                      )
                      .map(blocker => (
                        <li key={blocker.code}>
                          {BLOCKER_CODES.includes(
                            blocker.code as (typeof BLOCKER_CODES)[number],
                          )
                            ? t(`cancellation.blockers.${blocker.code}`, {
                                count: blocker.count,
                              })
                            : t('cancellation.blockers.unknown')}
                        </li>
                      ))}
                  </ul>
                </div>
              ) : null}
              {preview?.published_courses.length ? (
                <div className='space-y-2 rounded-lg border p-3'>
                  <p className='text-sm'>
                    {t('cancellation.transferRequired', {
                      count: preview.published_courses.length,
                    })}
                  </p>
                  <div className='flex gap-2'>
                    <Input
                      value={identifier}
                      onChange={event => setIdentifier(event.target.value)}
                      placeholder={t(
                        contactType === 'email'
                          ? 'cancellation.transferEmailPlaceholder'
                          : 'cancellation.transferPhonePlaceholder',
                      )}
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
              <div className='space-y-2'>
                <label
                  className='text-sm font-medium text-foreground'
                  htmlFor='account-cancellation-reason'
                >
                  {t('cancellation.reasonLabel')}
                </label>
                <Textarea
                  id='account-cancellation-reason'
                  className='min-h-28 resize-none'
                  value={reason}
                  maxLength={500}
                  onChange={event => setReason(event.target.value)}
                  placeholder={t('cancellation.reasonPlaceholder')}
                />
                <div className='flex items-start justify-between gap-3 text-xs'>
                  <p
                    className={
                      reason.length > 0 && reasonLength < 5
                        ? 'text-destructive'
                        : 'text-muted-foreground'
                    }
                  >
                    {reason.length > 0 && reasonLength < 5
                      ? t('cancellation.reasonTooShort')
                      : t('cancellation.reasonHint')}
                  </p>
                  <span className='shrink-0 text-muted-foreground'>
                    {t('cancellation.reasonCounter', {
                      count: reason.length,
                    })}
                  </span>
                </div>
              </div>
            </div>
          ) : (
            <div className='space-y-3'>
              {preview?.paid_preorder_count ? (
                <div className='rounded-lg border border-amber-200 bg-amber-50/60 px-4 py-3 text-sm text-amber-800'>
                  {t('cancellation.confirmPaidPreorder', {
                    count: preview.paid_preorder_count,
                  })}
                </div>
              ) : null}
              <div className='rounded-xl border border-destructive/25 bg-destructive/5 px-4 py-3 text-sm'>
                {t('cancellation.irreversible')}
              </div>
              <dl className='rounded-xl border border-border/70 px-4 py-3 text-sm'>
                <dt className='text-muted-foreground'>
                  {t('cancellation.summary.accountLabel')}
                </dt>
                <dd className='mt-1 break-all font-medium'>
                  {accountIdentifier}
                </dd>
                <dt className='mt-3 text-muted-foreground'>
                  {t('cancellation.reasonLabel')}
                </dt>
                <dd className='mt-1 whitespace-pre-wrap'>{reason.trim()}</dd>
              </dl>
            </div>
          )}
        </div>
        <DialogFooter className='px-5 py-4'>
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
            variant={confirming ? 'destructive' : 'default'}
            disabled={cannotContinue}
            onClick={confirming ? cancelAccount : prepare}
          >
            {confirming && busy
              ? t('cancellation.processing')
              : confirming
                ? t('cancellation.confirm')
                : t('cancellation.continue')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
