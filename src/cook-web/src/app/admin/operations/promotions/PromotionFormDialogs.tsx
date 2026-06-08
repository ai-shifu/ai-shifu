import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronUp } from 'lucide-react';
import type {
  AdminBillingCampaignDetail,
  AdminBillingCampaignProductOptions,
  AdminPromotionCampaignItem,
  AdminPromotionCouponItem,
} from '@/app/admin/operations/operation-promotion-types';
import { Button } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Checkbox';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import { Textarea } from '@/components/ui/Textarea';
import { showDefaultToast, showErrorToast } from '@/hooks/useToast';
import {
  formatBillingCreditAmount,
  formatBillingPlanInterval,
  formatBillingPrice,
  resolveBillingPlanValidityLabel,
} from '@/lib/billing';
import { cn } from '@/lib/utils';
import type { BillingPlan } from '@/types/billing';
import PromotionDateTimePicker from './PromotionDateTimePicker';
import {
  type CampaignFormState,
  type CouponFormState,
  type PackageCampaignFormState,
  type PackageCampaignProductRuleFormState,
  createDefaultPackageCampaignForm,
  createDefaultPackageCampaignProductRule,
  createCampaignFormFromItem,
  createCouponFormFromItem,
  createDefaultCampaignForm,
  createDefaultCouponForm,
  createPackageCampaignFormFromDetail,
  DEFAULT_END_TIME,
  DEFAULT_START_TIME,
  FormField,
  isPackageCampaignTrialOption,
  isPositiveIntegerString,
  PackageCampaignInlineField,
  PackageCampaignInlineValueField,
  parseCampaignPriceInputToMinor,
  parseLocalDateTimeInput,
  parsePositiveCampaignNumberInput,
  resolveCampaignPriceCurrencySymbol,
  resolvePackageCampaignOptionTitle,
  SINGLE_SELECT_ITEM_CLASS,
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
            <div className='relative'>
              <Input
                className={cn('h-9', isPercentDiscount && 'pr-8')}
                value={form.value}
                placeholder={valuePlaceholder}
                onChange={event =>
                  setForm(current => ({
                    ...current,
                    value: event.target.value,
                  }))
                }
                disabled={isEditing}
              />
              {isPercentDiscount ? (
                <span className='pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-muted-foreground'>
                  %
                </span>
              ) : null}
            </div>
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
            <div className='relative'>
              <Input
                className={cn('h-9', isPercentDiscount && 'pr-8')}
                value={form.value}
                placeholder={valuePlaceholder}
                onChange={event =>
                  setForm(current => ({
                    ...current,
                    value: event.target.value,
                  }))
                }
                disabled={isEditing}
              />
              {isPercentDiscount ? (
                <span className='pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-muted-foreground'>
                  %
                </span>
              ) : null}
            </div>
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
export const PackageCampaignDialog = ({
  open,
  onOpenChange,
  onSubmit,
  campaign,
  productOptions,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (payload: PackageCampaignFormState) => Promise<void>;
  campaign?: AdminBillingCampaignDetail | null;
  productOptions: AdminBillingCampaignProductOptions | null;
}) => {
  const { t, i18n } = useTranslation();
  const { t: tPromotion } = useTranslation('module.operationsPromotion');
  const [form, setForm] = useState<PackageCampaignFormState>(() =>
    createDefaultPackageCampaignForm(),
  );
  const [submitting, setSubmitting] = useState(false);
  const [productsExpanded, setProductsExpanded] = useState(true);

  useEffect(() => {
    if (open) {
      setProductsExpanded(true);
      setForm(
        campaign
          ? createPackageCampaignFormFromDetail(campaign)
          : createDefaultPackageCampaignForm(),
      );
    }
  }, [campaign, open]);

  const isEditing = Boolean(campaign);
  const isDiscount = form.benefit_type === 'discount';
  const availableOptions = (
    form.product_type === 'topup'
      ? productOptions?.topups || []
      : form.product_type === 'plan'
        ? productOptions?.plans || []
        : []
  ).filter(option => !isPackageCampaignTrialOption(option));
  const selectedProductOptions = availableOptions.filter(option =>
    form.product_bids.includes(option.product_bid),
  );

  const handleToggleProduct = (productBid: string, checked: boolean) => {
    setForm(current => ({
      ...current,
      product_bids: checked
        ? [...current.product_bids, productBid]
        : current.product_bids.filter(item => item !== productBid),
      product_rules: checked
        ? {
            ...current.product_rules,
            [productBid]:
              current.product_rules[productBid] ||
              createDefaultPackageCampaignProductRule(
                current.discount_type || 'fixed',
              ),
          }
        : Object.fromEntries(
            Object.entries(current.product_rules).filter(
              ([currentProductBid]) => currentProductBid !== productBid,
            ),
          ),
    }));
  };

  const handleProductRuleChange = (
    productBid: string,
    patch: Partial<PackageCampaignProductRuleFormState>,
  ) => {
    setForm(current => ({
      ...current,
      product_rules: {
        ...current.product_rules,
        [productBid]: {
          ...(current.product_rules[productBid] ||
            createDefaultPackageCampaignProductRule(
              current.discount_type || 'fixed',
            )),
          ...patch,
        },
      },
    }));
  };

  const handleSubmit = async () => {
    if (!form.name.trim()) {
      showDefaultToast(tPromotion('validation.packageCampaignNameRequired'));
      return;
    }
    if (!form.product_type) {
      showDefaultToast(
        tPromotion('validation.packageCampaignProductTypeRequired'),
      );
      return;
    }
    if (!form.product_bids.length) {
      showDefaultToast(
        tPromotion('validation.packageCampaignProductsRequired'),
      );
      return;
    }
    if (!form.benefit_type) {
      showDefaultToast(
        tPromotion('validation.packageCampaignBenefitTypeRequired'),
      );
      return;
    }
    if (isDiscount && !form.discount_type) {
      showDefaultToast(tPromotion('validation.discountTypeRequired'));
      return;
    }
    for (const option of selectedProductOptions) {
      const productRule =
        form.product_rules[option.product_bid] ||
        createDefaultPackageCampaignProductRule(form.discount_type || 'fixed');
      if (isDiscount) {
        if (form.discount_type === 'fixed') {
          const campaignPriceAmount = parseCampaignPriceInputToMinor(
            productRule.campaign_price,
            option.currency,
          );
          if (
            campaignPriceAmount === null ||
            campaignPriceAmount <= 0 ||
            campaignPriceAmount >= option.price_amount
          ) {
            showDefaultToast(
              tPromotion('validation.packageCampaignPriceInvalid'),
            );
            return;
          }
        } else {
          const discountPercent = parsePositiveCampaignNumberInput(
            productRule.discount_percent,
          );
          if (discountPercent === null || discountPercent > 100) {
            showDefaultToast(tPromotion('validation.valuePercentInvalid'));
            return;
          }
        }
      } else if (
        parsePositiveCampaignNumberInput(productRule.bonus_credit_amount) ===
        null
      ) {
        showDefaultToast(tPromotion('validation.packageCampaignBonusInvalid'));
        return;
      }
    }
    const startAtDate = parseLocalDateTimeInput(form.start_at);
    const endAtDate = parseLocalDateTimeInput(form.end_at);
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
      endAtDate.getTime() <= startAtDate.getTime()
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
      <DialogContent className='flex max-h-[min(92vh,880px)] flex-col overflow-hidden sm:max-w-[880px]'>
        <DialogHeader>
          <DialogTitle>
            {isEditing
              ? tPromotion('packageCampaign.editDialogTitle')
              : tPromotion('packageCampaign.dialogTitle')}
          </DialogTitle>
        </DialogHeader>
        <div className='min-h-0 flex-1 overflow-y-auto pr-1'>
          <div className='grid gap-x-4 gap-y-5 md:grid-cols-2 xl:grid-cols-3'>
            <FormField label={tPromotion('packageCampaign.name')}>
              <Input
                className='h-9'
                value={form.name}
                placeholder={tPromotion('packageCampaign.namePlaceholder')}
                onChange={event =>
                  setForm(current => ({ ...current, name: event.target.value }))
                }
              />
            </FormField>
            <FormField label={tPromotion('packageCampaign.productType')}>
              <Select
                value={form.product_type}
                onValueChange={value =>
                  setForm(current => ({
                    ...current,
                    product_type: value,
                    product_bids: [],
                    product_rules: {},
                  }))
                }
              >
                <SelectTrigger className='h-9'>
                  <SelectValue
                    placeholder={tPromotion(
                      'packageCampaign.productTypePlaceholder',
                    )}
                  />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem
                    value='plan'
                    className={SINGLE_SELECT_ITEM_CLASS}
                  >
                    {tPromotion('packageCampaign.productTypePlan')}
                  </SelectItem>
                  <SelectItem
                    value='topup'
                    className={SINGLE_SELECT_ITEM_CLASS}
                  >
                    {tPromotion('packageCampaign.productTypeTopup')}
                  </SelectItem>
                </SelectContent>
              </Select>
            </FormField>
            <FormField label={tPromotion('packageCampaign.benefitType')}>
              <Select
                value={form.benefit_type}
                onValueChange={value =>
                  setForm(current => {
                    const resolvedDiscountType =
                      value === 'discount'
                        ? current.discount_type || 'fixed'
                        : '';
                    return {
                      ...current,
                      benefit_type: value,
                      discount_type: resolvedDiscountType,
                      product_rules:
                        value === 'bonus'
                          ? current.product_rules
                          : Object.fromEntries(
                              Object.entries(current.product_rules).map(
                                ([productBid, rule]) => [
                                  productBid,
                                  {
                                    ...rule,
                                    discount_type: resolvedDiscountType,
                                  },
                                ],
                              ),
                            ),
                    };
                  })
                }
              >
                <SelectTrigger className='h-9'>
                  <SelectValue
                    placeholder={tPromotion(
                      'packageCampaign.benefitTypePlaceholder',
                    )}
                  />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem
                    value='discount'
                    className={SINGLE_SELECT_ITEM_CLASS}
                  >
                    {tPromotion('packageCampaign.benefitTypeDiscount')}
                  </SelectItem>
                  <SelectItem
                    value='bonus'
                    className={SINGLE_SELECT_ITEM_CLASS}
                  >
                    {tPromotion('packageCampaign.benefitTypeBonus')}
                  </SelectItem>
                </SelectContent>
              </Select>
            </FormField>
            {isDiscount ? (
              <FormField
                label={tPromotion('packageCampaign.productDiscountType')}
              >
                <Select
                  value={form.discount_type}
                  onValueChange={value =>
                    setForm(current => ({
                      ...current,
                      discount_type: value,
                      product_rules: Object.fromEntries(
                        Object.entries(current.product_rules).map(
                          ([productBid, rule]) => [
                            productBid,
                            {
                              ...rule,
                              discount_type: value,
                              campaign_price:
                                value === 'fixed' ? rule.campaign_price : '',
                              discount_percent:
                                value === 'percent'
                                  ? rule.discount_percent
                                  : '',
                            },
                          ],
                        ),
                      ),
                    }))
                  }
                >
                  <SelectTrigger className='h-9'>
                    <SelectValue
                      placeholder={tPromotion('filters.discountType')}
                    />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem
                      value='fixed'
                      className={SINGLE_SELECT_ITEM_CLASS}
                    >
                      {tPromotion('discountType.fixed')}
                    </SelectItem>
                    <SelectItem
                      value='percent'
                      className={SINGLE_SELECT_ITEM_CLASS}
                    >
                      {tPromotion('discountType.percent')}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </FormField>
            ) : null}
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
                  setForm(current => ({ ...current, start_at: nextValue }))
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
                  setForm(current => ({ ...current, end_at: nextValue }))
                }
              />
            </FormField>
            <div className='md:col-span-2 xl:col-span-3'>
              <div className='space-y-2'>
                <div className='flex items-start justify-between gap-3'>
                  <div className='min-w-0 space-y-1'>
                    <Label className='text-sm font-medium text-foreground leading-none'>
                      {tPromotion('packageCampaign.products')}
                    </Label>
                    <p className='text-xs leading-5 text-muted-foreground'>
                      {tPromotion('packageCampaign.productsHelper')}
                    </p>
                  </div>
                  <Button
                    type='button'
                    size='icon'
                    variant='ghost'
                    className='h-8 w-8 rounded-full border border-border bg-background text-muted-foreground hover:text-foreground'
                    aria-label={tPromotion('packageCampaign.products')}
                    onClick={() => setProductsExpanded(current => !current)}
                  >
                    {productsExpanded ? (
                      <ChevronUp className='h-4 w-4' />
                    ) : (
                      <ChevronDown className='h-4 w-4' />
                    )}
                  </Button>
                </div>
                <div
                  className={cn('pt-1', productsExpanded ? 'block' : 'hidden')}
                >
                  <div className='grid max-h-[min(18rem,34vh)] gap-2.5 overflow-y-auto pr-1 xl:grid-cols-2'>
                    {!form.product_type ? (
                      <div className='xl:col-span-2 text-sm text-muted-foreground'>
                        {tPromotion('packageCampaign.productsEmptyHint')}
                      </div>
                    ) : availableOptions.length === 0 ? (
                      <div className='xl:col-span-2 text-sm text-muted-foreground'>
                        {tPromotion('packageCampaign.productsUnavailable')}
                      </div>
                    ) : (
                      availableOptions.map(option => {
                        const checked = form.product_bids.includes(
                          option.product_bid,
                        );
                        const title = resolvePackageCampaignOptionTitle(
                          t,
                          option,
                        );
                        const productRule =
                          form.product_rules[option.product_bid] ||
                          createDefaultPackageCampaignProductRule(
                            form.discount_type || 'fixed',
                          );
                        const detail =
                          option.product_type === 'plan'
                            ? `${formatBillingPrice(
                                option.price_amount,
                                option.currency,
                                i18n.language,
                              )} · ${formatBillingPlanInterval(
                                t,
                                option as unknown as BillingPlan,
                              )} · ${resolveBillingPlanValidityLabel(
                                t,
                                option as unknown as BillingPlan,
                              )}`
                            : `${formatBillingPrice(
                                option.price_amount,
                                option.currency,
                                i18n.language,
                              )} · ${tPromotion(
                                'packageCampaign.productCredits',
                                {
                                  value: formatBillingCreditAmount(
                                    option.credit_amount,
                                  ),
                                },
                              )}`;
                        return (
                          <div
                            key={option.product_bid}
                            className={cn(
                              'self-start rounded-xl border px-4 py-3 transition-colors',
                              checked
                                ? 'border-border bg-background shadow-sm'
                                : 'border-border/70 bg-background hover:border-border hover:bg-muted/20',
                            )}
                          >
                            <label className='flex cursor-pointer items-start gap-3'>
                              <Checkbox
                                checked={checked}
                                onCheckedChange={value =>
                                  handleToggleProduct(
                                    option.product_bid,
                                    Boolean(value),
                                  )
                                }
                              />
                              <div className='min-w-0 flex-1'>
                                <div className='text-sm font-medium text-foreground'>
                                  {title}
                                </div>
                                <div className='mt-0.5 text-xs leading-5 text-muted-foreground'>
                                  {detail}
                                </div>
                              </div>
                            </label>
                            {checked ? (
                              <div className='mt-2.5 space-y-2.5 border-t border-border/70 pt-2.5'>
                                <div className='grid gap-2.5 md:grid-cols-2'>
                                  <PackageCampaignInlineValueField
                                    label={tPromotion(
                                      'packageCampaign.originalPrice',
                                    )}
                                    value={formatBillingPrice(
                                      option.price_amount,
                                      option.currency,
                                      i18n.language,
                                    )}
                                  />
                                  <PackageCampaignInlineValueField
                                    label={tPromotion(
                                      'packageCampaign.originalCredits',
                                    )}
                                    value={formatBillingCreditAmount(
                                      option.credit_amount,
                                    )}
                                  />
                                  {isDiscount ? (
                                    <>
                                      <PackageCampaignInlineField
                                        label={
                                          form.discount_type === 'percent'
                                            ? tPromotion(
                                                'packageCampaign.productDiscountPercent',
                                              )
                                            : tPromotion(
                                                'packageCampaign.campaignPrice',
                                              )
                                        }
                                      >
                                        <div className='flex items-center gap-2'>
                                          {form.discount_type ===
                                          'percent' ? null : (
                                            <span className='shrink-0 text-sm text-muted-foreground'>
                                              {resolveCampaignPriceCurrencySymbol(
                                                option.currency,
                                              )}
                                            </span>
                                          )}
                                          <Input
                                            className={cn(
                                              'h-7 min-w-0 border-0 bg-transparent px-0 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0',
                                              form.discount_type ===
                                                'percent' &&
                                                'min-w-[4rem] flex-1',
                                            )}
                                            value={
                                              form.discount_type === 'percent'
                                                ? productRule.discount_percent
                                                : productRule.campaign_price
                                            }
                                            placeholder={
                                              form.discount_type === 'percent'
                                                ? ''
                                                : tPromotion(
                                                    'packageCampaign.campaignPricePlaceholder',
                                                  )
                                            }
                                            onChange={event =>
                                              handleProductRuleChange(
                                                option.product_bid,
                                                {
                                                  [form.discount_type ===
                                                  'percent'
                                                    ? 'discount_percent'
                                                    : 'campaign_price']:
                                                    event.target.value,
                                                },
                                              )
                                            }
                                          />
                                          {form.discount_type === 'percent' ? (
                                            <span className='shrink-0 text-sm text-muted-foreground'>
                                              %
                                            </span>
                                          ) : null}
                                        </div>
                                      </PackageCampaignInlineField>
                                    </>
                                  ) : form.benefit_type === 'bonus' ? (
                                    <PackageCampaignInlineField
                                      label={tPromotion(
                                        'packageCampaign.bonusCreditAmount',
                                      )}
                                    >
                                      <Input
                                        className='h-7 border-0 bg-transparent px-0 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0'
                                        value={productRule.bonus_credit_amount}
                                        placeholder={tPromotion(
                                          'packageCampaign.bonusCreditAmountPlaceholder',
                                        )}
                                        onChange={event =>
                                          handleProductRuleChange(
                                            option.product_bid,
                                            {
                                              bonus_credit_amount:
                                                event.target.value,
                                            },
                                          )
                                        }
                                      />
                                    </PackageCampaignInlineField>
                                  ) : null}
                                </div>
                              </div>
                            ) : null}
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              </div>
            </div>
            <div className='md:col-span-2 xl:col-span-3'>
              <FormField label={tPromotion('packageCampaign.note')}>
                <Textarea
                  value={form.note}
                  placeholder={tPromotion('packageCampaign.notePlaceholder')}
                  onChange={event =>
                    setForm(current => ({
                      ...current,
                      note: event.target.value,
                    }))
                  }
                />
              </FormField>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button
            type='button'
            variant='outline'
            onClick={() => onOpenChange(false)}
            disabled={submitting}
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
