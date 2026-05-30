'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { QuestionMarkCircleIcon } from '@heroicons/react/24/outline';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import PromotionDateTimePicker from '@/app/admin/operations/promotions/PromotionDateTimePicker';
import {
  DEFAULT_END_TIME,
  DEFAULT_START_TIME,
  FormField,
  createCouponFormFromItem,
  isPositiveIntegerString,
  parseLocalDateTimeInput,
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
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { showDefaultToast, showErrorToast } from '@/hooks/useToast';
import type { Shifu } from '@/types/shifu';
import type { AdminPromotionCouponItem } from '@/app/admin/operations/operation-promotion-types';

const SELECT_ITEM_CLASS =
  'pl-3 pr-8 data-[state=checked]:bg-muted data-[state=checked]:text-foreground';
const SELECT_ITEM_INDICATOR_CLASS = 'left-auto right-2';
const MAX_COURSE_PAGES = 50;

const createDefaultCreatorCouponForm = (): CouponFormState => ({
  name: '',
  code: '',
  usage_type: '',
  discount_type: '',
  value: '',
  total_count: '',
  scope_type: 'single_course',
  shifu_bid: '',
  start_at: '',
  end_at: '',
  enabled: 'true',
});

const CreatorRedemptionCodeDialog = ({
  open,
  onOpenChange,
  onSuccess,
  coupon,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
  coupon?: AdminPromotionCouponItem | null;
}) => {
  const { t } = useTranslation();
  const { t: tPromotion } = useTranslation('module.operationsPromotion');
  const [form, setForm] = useState<CouponFormState>(() =>
    createDefaultCreatorCouponForm(),
  );
  const [courses, setCourses] = useState<Shifu[]>([]);
  const [coursesLoading, setCoursesLoading] = useState(false);
  const [coursesError, setCoursesError] = useState('');
  const [coursesWarning, setCoursesWarning] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const isEditing = Boolean(coupon);

  useEffect(() => {
    if (!open) {
      return;
    }
    setForm(
      coupon
        ? createCouponFormFromItem(coupon)
        : createDefaultCreatorCouponForm(),
    );
  }, [coupon, open]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    let canceled = false;
    const loadCourses = async () => {
      setCoursesLoading(true);
      setCoursesError(current => (current ? '' : current));
      setCoursesWarning(current => (current ? '' : current));
      try {
        const pageSize = 100;
        let pageIndex = 1;
        let reachedLimit = false;
        const collected: Shifu[] = [];
        const seen = new Set<string>();

        while (!canceled && pageIndex <= MAX_COURSE_PAGES) {
          const response = (await api.getAdminOrderShifus({
            page_index: pageIndex,
            page_size: pageSize,
            published: true,
          })) as { items?: Shifu[] };
          const pageItems = response.items || [];
          pageItems.forEach(course => {
            if (course?.bid && !seen.has(course.bid)) {
              seen.add(course.bid);
              collected.push(course);
            }
          });
          if (pageItems.length < pageSize) {
            break;
          }
          pageIndex += 1;
        }
        if (pageIndex > MAX_COURSE_PAGES) {
          reachedLimit = true;
        }

        if (!canceled) {
          setCourses(collected);
          if (reachedLimit) {
            setCoursesWarning(t('module.order.redemptionCodes.tooManyCourses'));
          }
        }
      } catch (error) {
        if (!canceled) {
          setCourses([]);
          setCoursesError(
            (error as Error).message ||
              t('module.order.redemptionCodes.loadCoursesFailed'),
          );
        }
      } finally {
        if (!canceled) {
          setCoursesLoading(false);
        }
      }
    };

    void loadCourses();
    return () => {
      canceled = true;
    };
  }, [open, t]);

  const isGenericCoupon = form.usage_type === '801';
  const isPercentDiscount = form.discount_type === '702';
  const valueLabel = isPercentDiscount
    ? tPromotion('coupon.valuePercent')
    : tPromotion('coupon.valueAmount');
  const valuePlaceholder = isPercentDiscount
    ? tPromotion('coupon.valuePercentPlaceholder')
    : tPromotion('coupon.valueAmountPlaceholder');

  const courseOptions = useMemo(
    () => courses.filter(course => Boolean(String(course.bid || '').trim())),
    [courses],
  );

  const handleSubmit = async () => {
    const normalizedName = (form.name || '').trim();
    const normalizedCode = (form.code || '').trim();
    const normalizedQuantity = (form.total_count || '').trim();
    const normalizedCourseId = (form.shifu_bid || '').trim();
    const normalizedValue = (form.value || '').trim();
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

    if (isGenericCoupon && !normalizedCode) {
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
    if (!normalizedCourseId) {
      showDefaultToast(t('module.order.redemptionCodes.courseRequired'));
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
      const payload = {
        ...form,
        code: normalizedCode,
        name: normalizedName,
        scope_type: 'single_course',
        shifu_bid: normalizedCourseId,
        total_count: normalizedQuantity,
        value: normalizedValue,
        enabled: true,
      };
      if (isEditing && coupon) {
        await api.updateCreatorCourseRedemptionCode({
          ...payload,
          coupon_bid: coupon.coupon_bid,
        });
      } else {
        await api.createCreatorCourseRedemptionCode(payload);
      }
      showDefaultToast(
        isEditing
          ? t('module.order.redemptionCodes.updateSuccess')
          : t('module.order.redemptionCodes.createSuccess'),
      );
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
      <DialogContent className='sm:max-w-[680px]'>
        <DialogHeader>
          <DialogTitle>
            {isEditing
              ? t('module.order.redemptionCodes.editDialogTitle')
              : t('module.order.redemptionCodes.dialogTitle')}
          </DialogTitle>
          <DialogDescription className='sr-only'>
            {isEditing
              ? t('module.order.redemptionCodes.editDialogTitle')
              : t('module.order.redemptionCodes.dialogTitle')}
          </DialogDescription>
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
          <FormField
            label={
              <span className='inline-flex items-center gap-1.5'>
                {tPromotion('table.usageType')}
                <TooltipProvider delayDuration={0}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type='button'
                        className='inline-flex h-4 w-4 items-center justify-center rounded-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:ring-offset-2'
                        aria-label={t(
                          'module.order.redemptionCodes.usageTypeHelp',
                        )}
                      >
                        <QuestionMarkCircleIcon className='h-4 w-4' />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent className='z-[113] max-w-72 text-left text-xs leading-5'>
                      <div className='space-y-1'>
                        <div>
                          {t(
                            'module.order.redemptionCodes.usageTypeHelpGeneric',
                          )}
                        </div>
                        <div>
                          {t(
                            'module.order.redemptionCodes.usageTypeHelpSingleUse',
                          )}
                        </div>
                      </div>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </span>
            }
          >
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
                <SelectItem
                  value='801'
                  className={SELECT_ITEM_CLASS}
                  indicatorClassName={SELECT_ITEM_INDICATOR_CLASS}
                >
                  {tPromotion('usageType.generic')}
                </SelectItem>
                <SelectItem
                  value='802'
                  className={SELECT_ITEM_CLASS}
                  indicatorClassName={SELECT_ITEM_INDICATOR_CLASS}
                >
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
                <SelectItem
                  value='701'
                  className={SELECT_ITEM_CLASS}
                  indicatorClassName={SELECT_ITEM_INDICATOR_CLASS}
                >
                  {tPromotion('discountType.fixed')}
                </SelectItem>
                <SelectItem
                  value='702'
                  className={SELECT_ITEM_CLASS}
                  indicatorClassName={SELECT_ITEM_INDICATOR_CLASS}
                >
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
          {isGenericCoupon ? (
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
          ) : null}
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
          <FormField label={t('module.order.redemptionCodes.courseLabel')}>
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
                          indicatorClassName={SELECT_ITEM_INDICATOR_CLASS}
                        >
                          {course.name || course.bid}
                        </SelectItem>
                      ))
                    )}
                  </>
                )}
              </SelectContent>
            </Select>
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
            {submitting
              ? t('module.order.redemptionCodes.submitting')
              : isEditing
                ? tPromotion('actions.confirmUpdate')
                : tPromotion('actions.confirmCreate')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default CreatorRedemptionCodeDialog;
