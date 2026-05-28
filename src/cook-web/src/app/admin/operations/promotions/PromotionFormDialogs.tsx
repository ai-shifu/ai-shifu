import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type {
  AdminPromotionCampaignItem,
  AdminPromotionCouponItem,
} from '@/app/admin/operations/operation-promotion-types';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import { Textarea } from '@/components/ui/Textarea';
import { showDefaultToast, showErrorToast } from '@/hooks/useToast';
import PromotionDateTimePicker from './PromotionDateTimePicker';
import {
  type CampaignFormState,
  type CouponFormState,
  createCampaignFormFromItem,
  createCouponFormFromItem,
  createDefaultCampaignForm,
  createDefaultCouponForm,
  DEFAULT_END_TIME,
  DEFAULT_START_TIME,
  FormField,
  isPositiveIntegerString,
  parseLocalDateTimeInput,
} from './promotionPageShared';

export const PromotionCouponDialog = ({
  open,
  onOpenChange,
  onSubmit,
  coupon,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (payload: CouponFormState) => Promise<void>;
  coupon?: AdminPromotionCouponItem | null;
}) => {
  const { t } = useTranslation();
  const { t: tPromotion } = useTranslation('module.operationsPromotion');
  const [form, setForm] = useState<CouponFormState>(() =>
    createDefaultCouponForm(),
  );
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(
        coupon ? createCouponFormFromItem(coupon) : createDefaultCouponForm(),
      );
    }
  }, [coupon, open]);

  const isEditing = Boolean(coupon);
  const isSingleUseCoupon = form.usage_type === '802';
  const isPercentDiscount = form.discount_type === '702';
  const valueLabel = isPercentDiscount
    ? tPromotion('coupon.valuePercent')
    : tPromotion('coupon.valueAmount');
  const valuePlaceholder = isPercentDiscount
    ? tPromotion('coupon.valuePercentPlaceholder')
    : tPromotion('coupon.valueAmountPlaceholder');

  const handleSubmit = async () => {
    const normalizedName = form.name.trim();
    const normalizedCode = form.code.trim();
    const normalizedQuantity = form.total_count.trim();
    const normalizedCourseId = form.shifu_bid.trim();
    const normalizedValue = form.value.trim();
    const startAtDate = parseLocalDateTimeInput(form.start_at);
    const endAtDate = parseLocalDateTimeInput(form.end_at);

    if (!normalizedName) {
      showDefaultToast(tPromotion('validation.couponNameRequired'));
      return;
    }
    if (!form.usage_type) {
      showDefaultToast(tPromotion('validation.usageTypeRequired'));
      return;
    }
    if (!form.discount_type) {
      showDefaultToast(tPromotion('validation.discountTypeRequired'));
      return;
    }
    if (!normalizedValue) {
      showDefaultToast(
        isPercentDiscount
          ? tPromotion('validation.valuePercentRequired')
          : tPromotion('validation.valueAmountRequired'),
      );
      return;
    }

    const numericValue = Number(normalizedValue);
    if (!Number.isFinite(numericValue)) {
      showDefaultToast(
        isPercentDiscount
          ? tPromotion('validation.valuePercentInvalid')
          : tPromotion('validation.valueAmountInvalid'),
      );
      return;
    }
    if (isPercentDiscount) {
      if (numericValue <= 0 || numericValue > 100) {
        showDefaultToast(tPromotion('validation.valuePercentInvalid'));
        return;
      }
    } else if (numericValue <= 0) {
      showDefaultToast(tPromotion('validation.valueAmountInvalid'));
      return;
    }

    if (!isSingleUseCoupon && !normalizedCode) {
      showDefaultToast(tPromotion('validation.codeRequired'));
      return;
    }
    if (!normalizedQuantity) {
      showDefaultToast(tPromotion('validation.quantityRequired'));
      return;
    }
    if (
      !isPositiveIntegerString(normalizedQuantity) ||
      Number(normalizedQuantity) <= 0
    ) {
      showDefaultToast(tPromotion('validation.quantityInvalid'));
      return;
    }
    if (form.scope_type === 'single_course' && !normalizedCourseId) {
      showDefaultToast(tPromotion('validation.courseIdRequired'));
      return;
    }
    if (!form.start_at) {
      showDefaultToast(tPromotion('validation.startAtRequired'));
      return;
    }
    if (!form.end_at) {
      showDefaultToast(tPromotion('validation.endAtRequired'));
      return;
    }
    if (
      !startAtDate ||
      !endAtDate ||
      endAtDate.getTime() < startAtDate.getTime()
    ) {
      showDefaultToast(tPromotion('validation.endAtInvalid'));
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit(form);
      onOpenChange(false);
    } catch (error) {
      showErrorToast((error as Error).message || t('common.core.submitFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className='sm:max-w-[680px]'>
        <DialogHeader>
          <DialogTitle>
            {isEditing
              ? tPromotion('coupon.editDialogTitle')
              : tPromotion('coupon.dialogTitle')}
          </DialogTitle>
        </DialogHeader>
        <div className='grid gap-4 md:grid-cols-2'>
          <FormField label={tPromotion('table.name')}>
            <Input
              className='h-9'
              value={form.name}
              placeholder={tPromotion('filters.namePlaceholder')}
              onChange={event =>
                setForm(current => ({ ...current, name: event.target.value }))
              }
            />
          </FormField>
          <FormField label={tPromotion('table.usageType')}>
            <Select
              value={form.usage_type}
              onValueChange={value =>
                setForm(current => ({
                  ...current,
                  usage_type: value,
                  code: value === '801' ? current.code : '',
                }))
              }
              disabled={isEditing}
            >
              <SelectTrigger className='h-9'>
                <SelectValue placeholder={tPromotion('filters.usageType')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='801'>
                  {tPromotion('usageType.generic')}
                </SelectItem>
                <SelectItem value='802'>
                  {tPromotion('usageType.singleUse')}
                </SelectItem>
              </SelectContent>
            </Select>
          </FormField>
          <FormField label={tPromotion('filters.discountType')}>
            <Select
              value={form.discount_type}
              onValueChange={value =>
                setForm(current => ({ ...current, discount_type: value }))
              }
              disabled={isEditing}
            >
              <SelectTrigger className='h-9'>
                <SelectValue placeholder={tPromotion('filters.discountType')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='701'>
                  {tPromotion('discountType.fixed')}
                </SelectItem>
                <SelectItem value='702'>
                  {tPromotion('discountType.percent')}
                </SelectItem>
              </SelectContent>
            </Select>
          </FormField>
          <FormField label={valueLabel}>
            <Input
              className='h-9'
              value={form.value}
              placeholder={valuePlaceholder}
              onChange={event =>
                setForm(current => ({ ...current, value: event.target.value }))
              }
              disabled={isEditing}
            />
          </FormField>
          {isSingleUseCoupon ? null : (
            <FormField label={tPromotion('coupon.code')}>
              <Input
                className='h-9'
                value={form.code}
                placeholder={tPromotion('coupon.codePlaceholder')}
                onChange={event =>
                  setForm(current => ({ ...current, code: event.target.value }))
                }
                disabled={isEditing}
              />
            </FormField>
          )}
          <FormField label={tPromotion('coupon.quantity')}>
            <Input
              className='h-9'
              value={form.total_count}
              placeholder={tPromotion('coupon.quantityPlaceholder')}
              onChange={event =>
                setForm(current => ({
                  ...current,
                  total_count: event.target.value,
                }))
              }
            />
          </FormField>
          <FormField label={tPromotion('coupon.scopeType')}>
            <Select
              value={form.scope_type}
              onValueChange={value =>
                setForm(current => ({
                  ...current,
                  scope_type: value,
                  shifu_bid: value === 'single_course' ? current.shifu_bid : '',
                }))
              }
              disabled={isEditing}
            >
              <SelectTrigger className='h-9'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='all_courses'>
                  {tPromotion('scope.allCourses')}
                </SelectItem>
                <SelectItem value='single_course'>
                  {tPromotion('scope.singleCourse')}
                </SelectItem>
              </SelectContent>
            </Select>
          </FormField>
          <FormField label={tPromotion('coupon.courseId')}>
            <Input
              className='h-9'
              value={form.shifu_bid}
              placeholder={tPromotion('filters.courseIdPlaceholder')}
              onChange={event =>
                setForm(current => ({
                  ...current,
                  shifu_bid: event.target.value,
                }))
              }
              disabled={isEditing || form.scope_type !== 'single_course'}
            />
          </FormField>
          <FormField label={tPromotion('coupon.startAt')}>
            <PromotionDateTimePicker
              value={form.start_at}
              placeholder={tPromotion('coupon.startAt')}
              resetLabel={t('module.order.filters.reset')}
              clearLabel={t('common.core.close')}
              timeLabel={tPromotion('coupon.startAt')}
              defaultTime={DEFAULT_START_TIME}
              maxDateTime={form.end_at}
              onChange={nextValue =>
                setForm(current => ({
                  ...current,
                  start_at: nextValue,
                }))
              }
            />
          </FormField>
          <FormField label={tPromotion('coupon.endAt')}>
            <PromotionDateTimePicker
              value={form.end_at}
              placeholder={tPromotion('coupon.endAt')}
              resetLabel={t('module.order.filters.reset')}
              clearLabel={t('common.core.close')}
              timeLabel={tPromotion('coupon.endAt')}
              defaultTime={DEFAULT_END_TIME}
              minDateTime={form.start_at}
              onChange={nextValue =>
                setForm(current => ({
                  ...current,
                  end_at: nextValue,
                }))
              }
            />
          </FormField>
        </div>
        <DialogFooter>
          <Button
            type='button'
            variant='outline'
            onClick={() => onOpenChange(false)}
          >
            {t('common.core.cancel')}
          </Button>
          <Button
            type='button'
            onClick={() => void handleSubmit()}
            disabled={submitting}
          >
            {isEditing
              ? tPromotion('actions.confirmUpdate')
              : tPromotion('actions.confirmCreate')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export const PromotionCampaignDialog = ({
  open,
  onOpenChange,
  onSubmit,
  campaign,
  strategyEditable,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (payload: CampaignFormState) => Promise<void>;
  campaign?: {
    item: AdminPromotionCampaignItem;
    description: string;
  } | null;
  strategyEditable?: boolean;
}) => {
  const { t } = useTranslation();
  const { t: tPromotion } = useTranslation('module.operationsPromotion');
  const [form, setForm] = useState<CampaignFormState>(() =>
    createDefaultCampaignForm(),
  );
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(
        campaign
          ? createCampaignFormFromItem(campaign.item, campaign.description)
          : createDefaultCampaignForm(),
      );
    }
  }, [campaign, open]);

  const isEditing = Boolean(campaign);

  const isPercentDiscount = form.discount_type === '702';
  const valueLabel = form.discount_type
    ? isPercentDiscount
      ? tPromotion('coupon.valuePercent')
      : tPromotion('coupon.valueAmount')
    : tPromotion('campaign.value');
  const valuePlaceholder = form.discount_type
    ? isPercentDiscount
      ? tPromotion('coupon.valuePercentPlaceholder')
      : tPromotion('coupon.valueAmountPlaceholder')
    : tPromotion('campaign.valuePlaceholder');

  const handleSubmit = async () => {
    const normalizedName = form.name.trim();
    const normalizedCourseId = form.shifu_bid.trim();
    const normalizedValue = form.value.trim();
    const startAtDate = parseLocalDateTimeInput(form.start_at);
    const endAtDate = parseLocalDateTimeInput(form.end_at);

    if (!normalizedName) {
      showDefaultToast(tPromotion('validation.campaignNameRequired'));
      return;
    }
    if (!form.apply_type) {
      showDefaultToast(tPromotion('validation.campaignApplyTypeRequired'));
      return;
    }
    if (!normalizedCourseId) {
      showDefaultToast(tPromotion('validation.courseIdRequired'));
      return;
    }
    if (!form.discount_type) {
      showDefaultToast(tPromotion('validation.discountTypeRequired'));
      return;
    }
    if (!normalizedValue) {
      showDefaultToast(
        isPercentDiscount
          ? tPromotion('validation.valuePercentRequired')
          : tPromotion('validation.valueAmountRequired'),
      );
      return;
    }
    const numericValue = Number(normalizedValue);
    if (!Number.isFinite(numericValue)) {
      showDefaultToast(
        isPercentDiscount
          ? tPromotion('validation.valuePercentInvalid')
          : tPromotion('validation.valueAmountInvalid'),
      );
      return;
    }
    if (isPercentDiscount) {
      if (numericValue <= 0 || numericValue > 100) {
        showDefaultToast(tPromotion('validation.valuePercentInvalid'));
        return;
      }
    } else if (numericValue <= 0) {
      showDefaultToast(tPromotion('validation.valueAmountInvalid'));
      return;
    }
    if (!form.start_at) {
      showDefaultToast(tPromotion('validation.startAtRequired'));
      return;
    }
    if (!form.end_at) {
      showDefaultToast(tPromotion('validation.endAtRequired'));
      return;
    }
    if (
      !startAtDate ||
      !endAtDate ||
      endAtDate.getTime() < startAtDate.getTime()
    ) {
      showDefaultToast(tPromotion('validation.endAtInvalid'));
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit(form);
      onOpenChange(false);
    } catch (error) {
      showErrorToast((error as Error).message || t('common.core.submitFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className='sm:max-w-[700px]'>
        <DialogHeader>
          <DialogTitle>
            {isEditing
              ? tPromotion('campaign.editDialogTitle')
              : tPromotion('campaign.dialogTitle')}
          </DialogTitle>
        </DialogHeader>
        <div className='grid gap-4 md:grid-cols-2'>
          <FormField label={tPromotion('table.campaignName')}>
            <Input
              className='h-9'
              value={form.name}
              placeholder={tPromotion('campaign.namePlaceholder')}
              onChange={event =>
                setForm(current => ({ ...current, name: event.target.value }))
              }
            />
          </FormField>
          <FormField label={tPromotion('coupon.courseId')}>
            <Input
              className='h-9'
              value={form.shifu_bid}
              placeholder={tPromotion('filters.courseIdPlaceholder')}
              onChange={event =>
                setForm(current => ({
                  ...current,
                  shifu_bid: event.target.value,
                }))
              }
              disabled={isEditing}
            />
          </FormField>
          <FormField label={tPromotion('campaign.applyType')}>
            <Select
              value={form.apply_type}
              onValueChange={value =>
                setForm(current => ({ ...current, apply_type: value }))
              }
              disabled={isEditing && !strategyEditable}
            >
              <SelectTrigger className='h-9'>
                <SelectValue
                  placeholder={tPromotion('campaign.applyTypePlaceholder')}
                />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='2101'>
                  {tPromotion('campaign.applyTypeAuto')}
                </SelectItem>
                <SelectItem value='2102'>
                  {tPromotion('campaign.applyTypeEvent')}
                </SelectItem>
                <SelectItem value='2103'>
                  {tPromotion('campaign.applyTypeManual')}
                </SelectItem>
              </SelectContent>
            </Select>
          </FormField>
          <FormField label={tPromotion('campaign.channel')}>
            <Input
              className='h-9'
              value={form.channel}
              placeholder={tPromotion('campaign.channelPlaceholder')}
              onChange={event =>
                setForm(current => ({
                  ...current,
                  channel: event.target.value,
                }))
              }
              disabled={isEditing}
            />
          </FormField>
          <FormField label={tPromotion('filters.discountType')}>
            <Select
              value={form.discount_type}
              onValueChange={value =>
                setForm(current => ({ ...current, discount_type: value }))
              }
              disabled={isEditing}
            >
              <SelectTrigger className='h-9'>
                <SelectValue placeholder={tPromotion('filters.discountType')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='701'>
                  {tPromotion('discountType.fixed')}
                </SelectItem>
                <SelectItem value='702'>
                  {tPromotion('discountType.percent')}
                </SelectItem>
              </SelectContent>
            </Select>
          </FormField>
          <FormField label={valueLabel}>
            <Input
              className='h-9'
              value={form.value}
              placeholder={valuePlaceholder}
              onChange={event =>
                setForm(current => ({ ...current, value: event.target.value }))
              }
              disabled={isEditing}
            />
          </FormField>
          <FormField label={tPromotion('campaign.startAt')}>
            <PromotionDateTimePicker
              value={form.start_at}
              placeholder={tPromotion('campaign.startAtPlaceholder')}
              resetLabel={t('module.order.filters.reset')}
              clearLabel={t('common.core.close')}
              timeLabel={tPromotion('campaign.startAt')}
              defaultTime={DEFAULT_START_TIME}
              maxDateTime={form.end_at}
              onChange={nextValue =>
                setForm(current => ({
                  ...current,
                  start_at: nextValue,
                }))
              }
            />
          </FormField>
          <FormField label={tPromotion('campaign.endAt')}>
            <PromotionDateTimePicker
              value={form.end_at}
              placeholder={tPromotion('campaign.endAtPlaceholder')}
              resetLabel={t('module.order.filters.reset')}
              clearLabel={t('common.core.close')}
              timeLabel={tPromotion('campaign.endAt')}
              defaultTime={DEFAULT_END_TIME}
              minDateTime={form.start_at}
              onChange={nextValue =>
                setForm(current => ({
                  ...current,
                  end_at: nextValue,
                }))
              }
            />
          </FormField>
          <div className='md:col-span-2'>
            <FormField label={tPromotion('campaign.description')}>
              <Textarea
                value={form.description}
                placeholder={tPromotion('campaign.descriptionPlaceholder')}
                onChange={event =>
                  setForm(current => ({
                    ...current,
                    description: event.target.value,
                  }))
                }
              />
            </FormField>
          </div>
        </div>
        <DialogFooter>
          <Button
            type='button'
            variant='outline'
            onClick={() => onOpenChange(false)}
          >
            {t('common.core.cancel')}
          </Button>
          <Button
            type='button'
            onClick={() => void handleSubmit()}
            disabled={submitting}
          >
            {isEditing
              ? tPromotion('actions.confirmUpdate')
              : tPromotion('actions.confirmCreate')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
