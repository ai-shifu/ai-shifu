'use client';

import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import PromotionDateTimePicker from '@/app/admin/operations/promotions/PromotionDateTimePicker';
import {
  DEFAULT_END_TIME,
  DEFAULT_START_TIME,
  FormField,
  type CouponFormState,
} from '@/app/admin/operations/promotions/promotionPageShared';
import Loading from '@/components/loading';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import { showDefaultToast, showErrorToast } from '@/hooks/useToast';
import type { AdminPromotionCouponItem } from '@/app/admin/operations/operation-promotion-types';
import {
  createCreatorCouponFormState,
  validateCreatorCouponForm,
} from './creatorRedemptionCodeDialogShared';
import { useCreatorPublishedCourseOptions } from './useCreatorPublishedCourseOptions';
import { useEnvStore } from '@/store/envStore';

const SELECT_ITEM_CLASS =
  'pl-3 pr-8 data-[state=checked]:bg-muted data-[state=checked]:text-foreground';

const CreatorRedemptionCodeDialog = ({
  open,
  onOpenChange,
  onSuccess,
  coupon,
  initialShifuBid,
  initialShifuName,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
  coupon?: AdminPromotionCouponItem | null;
  initialShifuBid?: string;
  initialShifuName?: string;
}) => {
  const { t } = useTranslation();
  const { t: tPromotion } = useTranslation('module.operationsPromotion');
  const currencySymbol = useEnvStore(state => state.currencySymbol);
  const [form, setForm] = useState<CouponFormState>(() =>
    createCreatorCouponFormState(),
  );
  const [submitting, setSubmitting] = useState(false);
  const isEditing = Boolean(coupon);
  const { courseOptions, coursesError, coursesLoading, coursesWarning } =
    useCreatorPublishedCourseOptions({
      open,
      t,
    });
  const lockedCourseName = React.useMemo(() => {
    if (!initialShifuBid) {
      return '';
    }
    const matchedCourse = courseOptions.find(
      course => course.bid === initialShifuBid,
    );
    return initialShifuName || matchedCourse?.name || initialShifuBid;
  }, [courseOptions, initialShifuBid, initialShifuName]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const nextForm = createCreatorCouponFormState(coupon);
    if (!coupon && initialShifuBid) {
      nextForm.shifu_bid = initialShifuBid;
    }
    setForm(nextForm);
  }, [coupon, initialShifuBid, open]);

  const isGenericCoupon = form.usage_type === '801';
  const isPercentDiscount = form.discount_type === '702';
  const valueLabel = isPercentDiscount
    ? t('module.order.redemptionCodes.valuePercentLabel')
    : t('module.order.redemptionCodes.valueAmountLabel', {
        currency: currencySymbol,
      });
  const valuePlaceholder = isPercentDiscount
    ? t('module.order.redemptionCodes.valuePercentPlaceholder')
    : t('module.order.redemptionCodes.valueAmountPlaceholder');

  const handleSubmit = async () => {
    const { errorKey, payload, submitSuccessKey } = validateCreatorCouponForm({
      form,
      isEditing,
      t,
      tPromotion,
    });
    if (errorKey || !payload || !submitSuccessKey) {
      showDefaultToast(errorKey);
      return;
    }

    setSubmitting(true);
    try {
      if (isEditing && coupon) {
        await api.updateCreatorCourseRedemptionCode({
          ...payload,
          coupon_bid: coupon.coupon_bid,
        });
      } else {
        await api.createCreatorCourseRedemptionCode(payload);
      }
      showDefaultToast(submitSuccessKey);
      onSuccess?.();
      onOpenChange(false);
    } catch (error) {
      showErrorToast(
        (error as Error).message ||
          t('module.order.redemptionCodes.createFailed'),
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className='max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-[680px]'>
        <DialogHeader>
          <DialogTitle>
            {isEditing
              ? t('module.order.redemptionCodes.editDialogTitle')
              : t('module.order.redemptionCodes.dialogTitle')}
          </DialogTitle>
          <DialogDescription className='leading-6'>
            {isEditing
              ? t('module.order.redemptionCodes.editDescription')
              : t('module.order.redemptionCodes.description')}
          </DialogDescription>
        </DialogHeader>
        <div className='grid gap-4 md:grid-cols-2'>
          <FormField label={t('module.order.redemptionCodes.nameLabel')}>
            <Input
              className='h-9'
              value={form.name}
              placeholder={t('module.order.redemptionCodes.namePlaceholder')}
              onChange={event =>
                setForm(current => ({ ...current, name: event.target.value }))
              }
            />
          </FormField>
          <FormField label={t('module.order.redemptionCodes.usageTypeLabel')}>
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
                <SelectValue
                  placeholder={t(
                    'module.order.redemptionCodes.usageTypePlaceholder',
                  )}
                />
              </SelectTrigger>
              <SelectContent>
                <SelectItem
                  value='801'
                  className={SELECT_ITEM_CLASS}
                >
                  {t('module.order.redemptionCodes.genericLabel')}
                </SelectItem>
                <SelectItem
                  value='802'
                  className={SELECT_ITEM_CLASS}
                >
                  {t('module.order.redemptionCodes.singleUseLabel')}
                </SelectItem>
              </SelectContent>
            </Select>
            <div className='space-y-1 text-xs leading-5 text-muted-foreground'>
              <p>{t('module.order.redemptionCodes.genericHint')}</p>
              <p>{t('module.order.redemptionCodes.singleUseHint')}</p>
            </div>
          </FormField>
          <FormField
            label={t('module.order.redemptionCodes.discountTypeLabel')}
          >
            <Select
              value={form.discount_type}
              onValueChange={value =>
                setForm(current => ({ ...current, discount_type: value }))
              }
              disabled={isEditing}
            >
              <SelectTrigger className='h-9'>
                <SelectValue
                  placeholder={t(
                    'module.order.redemptionCodes.discountTypePlaceholder',
                  )}
                />
              </SelectTrigger>
              <SelectContent>
                <SelectItem
                  value='701'
                  className={SELECT_ITEM_CLASS}
                >
                  {t('module.order.redemptionCodes.discountTypeFixed')}
                </SelectItem>
                <SelectItem
                  value='702'
                  className={SELECT_ITEM_CLASS}
                >
                  {t('module.order.redemptionCodes.discountTypePercent')}
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
            {isPercentDiscount ? (
              <p className='text-xs leading-5 text-muted-foreground'>
                {t('module.order.redemptionCodes.valuePercentHint')}
              </p>
            ) : null}
          </FormField>
          {isGenericCoupon ? (
            <FormField label={t('module.order.redemptionCodes.codeLabel')}>
              <Input
                className='h-9'
                value={form.code}
                placeholder={t('module.order.redemptionCodes.codePlaceholder')}
                onChange={event =>
                  setForm(current => ({ ...current, code: event.target.value }))
                }
                disabled={isEditing}
              />
            </FormField>
          ) : null}
          <FormField
            label={t(
              isGenericCoupon
                ? 'module.order.redemptionCodes.quantityLabelGeneric'
                : 'module.order.redemptionCodes.quantityLabelSingleUse',
            )}
          >
            <Input
              className='h-9'
              value={form.total_count}
              placeholder={t(
                'module.order.redemptionCodes.quantityPlaceholder',
              )}
              onChange={event =>
                setForm(current => ({
                  ...current,
                  total_count: event.target.value,
                }))
              }
            />
            {form.usage_type ? (
              <p className='text-xs leading-5 text-muted-foreground'>
                {t(
                  isGenericCoupon
                    ? 'module.order.redemptionCodes.quantityHintGeneric'
                    : 'module.order.redemptionCodes.quantityHintSingleUse',
                )}
              </p>
            ) : null}
          </FormField>
          <FormField label={t('module.order.redemptionCodes.courseLabel')}>
            {initialShifuBid && !isEditing ? (
              <Input
                className='h-9'
                value={lockedCourseName}
                readOnly
                disabled
              />
            ) : (
              <Select
                value={form.shifu_bid}
                onValueChange={value =>
                  setForm(current => ({ ...current, shifu_bid: value }))
                }
                disabled={coursesLoading || isEditing}
              >
                <SelectTrigger className='h-9'>
                  <SelectValue
                    placeholder={t(
                      'module.order.redemptionCodes.coursePlaceholder',
                    )}
                  />
                </SelectTrigger>
                <SelectContent className='max-h-60'>
                  {coursesLoading ? (
                    <div className='flex items-center justify-center py-3'>
                      <Loading className='h-5 w-5' />
                    </div>
                  ) : coursesError ? (
                    <div className='px-2 py-3 text-xs text-destructive'>
                      {coursesError}
                    </div>
                  ) : (
                    <>
                      {coursesWarning ? (
                        <div className='px-2 py-2 text-xs text-muted-foreground'>
                          {coursesWarning}
                        </div>
                      ) : null}
                      {courseOptions.length === 0 ? (
                        <div className='px-2 py-3 text-xs text-muted-foreground'>
                          {t('module.order.redemptionCodes.emptyCourses')}
                        </div>
                      ) : (
                        courseOptions.map(course => (
                          <SelectItem
                            key={course.bid}
                            value={course.bid}
                            className={SELECT_ITEM_CLASS}
                          >
                            {course.name || course.bid}
                          </SelectItem>
                        ))
                      )}
                    </>
                  )}
                </SelectContent>
              </Select>
            )}
          </FormField>
          <FormField label={t('module.order.redemptionCodes.startAtLabel')}>
            <PromotionDateTimePicker
              value={form.start_at}
              placeholder={t('module.order.redemptionCodes.startAtLabel')}
              resetLabel={t('module.order.filters.reset')}
              clearLabel={t('common.core.close')}
              timeLabel={t('module.order.redemptionCodes.startAtLabel')}
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
          <FormField label={t('module.order.redemptionCodes.endAtLabel')}>
            <PromotionDateTimePicker
              value={form.end_at}
              placeholder={t('module.order.redemptionCodes.endAtLabel')}
              resetLabel={t('module.order.filters.reset')}
              clearLabel={t('common.core.close')}
              timeLabel={t('module.order.redemptionCodes.endAtLabel')}
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
        <p className='text-xs leading-5 text-muted-foreground'>
          {t('module.order.redemptionCodes.dateRangeHint')}
        </p>
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
            {submitting
              ? isEditing
                ? t('common.core.submitting')
                : t('module.order.redemptionCodes.submitting')
              : isEditing
                ? tPromotion('actions.confirmUpdate')
                : t('module.order.redemptionCodes.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default CreatorRedemptionCodeDialog;
