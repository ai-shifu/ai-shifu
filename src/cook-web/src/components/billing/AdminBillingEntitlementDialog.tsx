'use client';

import React from 'react';
import { useSWRConfig } from 'swr';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { toast } from '@/hooks/useToast';
import type {
  AdminBillingEntitlementGrantPayload,
  AdminBillingEntitlementItem,
} from '@/types/billing';
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
import { Switch } from '@/components/ui/Switch';

type AdminBillingEntitlementDialogProps = {
  open: boolean;
  initialItem?: AdminBillingEntitlementItem | null;
  onOpenChange: (open: boolean) => void;
};

const ENTITLEMENT_FIELDS = [
  'branding_enabled',
  'custom_domain_enabled',
  'custom_wechat_enabled',
  'custom_payment_enabled',
] as const;

type EntitlementField = (typeof ENTITLEMENT_FIELDS)[number];

const EMPTY_VALUES: Record<EntitlementField, boolean> = {
  branding_enabled: false,
  custom_domain_enabled: false,
  custom_wechat_enabled: false,
  custom_payment_enabled: false,
};

function isEntitlementsCacheKey(key: unknown): boolean {
  if (Array.isArray(key)) {
    return key[0] === 'admin-billing-entitlements';
  }
  return key === 'admin-billing-entitlements';
}

export function AdminBillingEntitlementDialog({
  open,
  initialItem,
  onOpenChange,
}: AdminBillingEntitlementDialogProps) {
  const { t } = useTranslation();
  const { mutate } = useSWRConfig();
  const [creatorBid, setCreatorBid] = React.useState('');
  const [values, setValues] =
    React.useState<Record<EntitlementField, boolean>>(EMPTY_VALUES);
  const [submitting, setSubmitting] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    setCreatorBid(initialItem?.creator_bid || '');
    setValues(
      initialItem
        ? {
            branding_enabled: initialItem.branding_enabled,
            custom_domain_enabled: initialItem.custom_domain_enabled,
            custom_wechat_enabled: initialItem.custom_wechat_enabled,
            custom_payment_enabled: initialItem.custom_payment_enabled,
          }
        : EMPTY_VALUES,
    );
  }, [initialItem, open]);

  const handleSubmit = async () => {
    const normalizedCreatorBid = creatorBid.trim();
    if (!normalizedCreatorBid) {
      toast({
        title: t(
          'module.billing.admin.entitlements.grant.errors.creatorBidRequired',
        ),
        variant: 'destructive',
      });
      return;
    }

    setSubmitting(true);
    try {
      const payload: AdminBillingEntitlementGrantPayload = {
        creator_bid: normalizedCreatorBid,
        ...values,
      };
      await api.grantAdminBillingEntitlement(payload);
      await mutate(isEntitlementsCacheKey, undefined, { revalidate: true });
      onOpenChange(false);
      toast({
        title: t('module.billing.admin.entitlements.grant.success', {
          creatorBid: normalizedCreatorBid,
        }),
      });
    } catch {
      // The shared request layer already surfaces backend errors.
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
      <DialogContent className='border-slate-200 bg-white sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>
            {t(
              initialItem
                ? 'module.billing.admin.entitlements.grant.editTitle'
                : 'module.billing.admin.entitlements.grant.title',
            )}
          </DialogTitle>
          <DialogDescription>
            {t('module.billing.admin.entitlements.grant.description')}
          </DialogDescription>
        </DialogHeader>

        <div className='grid gap-4 py-2'>
          <div className='grid gap-2'>
            <label
              htmlFor='admin-billing-entitlement-creator-bid'
              className='text-sm font-medium text-slate-900'
            >
              {t('module.billing.admin.entitlements.grant.fields.creatorBid')}
            </label>
            <Input
              id='admin-billing-entitlement-creator-bid'
              value={creatorBid}
              disabled={Boolean(initialItem) || submitting}
              placeholder={t(
                'module.billing.admin.entitlements.grant.creatorBidPlaceholder',
              )}
              onChange={event => setCreatorBid(event.target.value)}
            />
          </div>

          {ENTITLEMENT_FIELDS.map(field => (
            <div
              key={field}
              className='flex items-center justify-between gap-4 rounded-lg border border-slate-200 px-4 py-3'
            >
              <label
                htmlFor={`admin-billing-entitlement-${field}`}
                className='text-sm font-medium text-slate-900'
              >
                {t(`module.billing.admin.entitlements.grant.fields.${field}`)}
              </label>
              <Switch
                id={`admin-billing-entitlement-${field}`}
                checked={values[field]}
                disabled={submitting}
                onCheckedChange={checked =>
                  setValues(current => ({ ...current, [field]: checked }))
                }
              />
            </div>
          ))}
        </div>

        <DialogFooter>
          <Button
            type='button'
            variant='outline'
            disabled={submitting}
            onClick={() => onOpenChange(false)}
          >
            {t('module.billing.admin.entitlements.grant.cancel')}
          </Button>
          <Button
            type='button'
            disabled={submitting}
            onClick={handleSubmit}
          >
            {submitting
              ? t('module.billing.admin.entitlements.grant.submitting')
              : t('module.billing.admin.entitlements.grant.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
