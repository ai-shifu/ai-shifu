import {
  createCouponFormFromItem,
  isPositiveIntegerString,
  parseLocalDateTimeInput,
  type CouponFormState,
} from '@/app/admin/operations/promotions/promotionPageShared';
import type { AdminPromotionCouponItem } from '@/app/admin/operations/operation-promotion-types';

type TranslationFn = (key: string, options?: Record<string, unknown>) => string;

export const createDefaultCreatorCouponForm = (): CouponFormState => ({
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

export const createCreatorCouponFormState = (
  coupon?: AdminPromotionCouponItem | null,
) =>
  coupon ? createCouponFormFromItem(coupon) : createDefaultCreatorCouponForm();

export const validateCreatorCouponForm = ({
  form,
  isEditing,
  t,
  tPromotion,
}: {
  form: CouponFormState;
  isEditing: boolean;
  t: TranslationFn;
  tPromotion: TranslationFn;
}) => {
  const normalizedName = (form.name || '').trim();
  const normalizedCode = (form.code || '').trim();
  const normalizedQuantity = (form.total_count || '').trim();
  const normalizedCourseId = (form.shifu_bid || '').trim();
  const normalizedValue = (form.value || '').trim();
  const startAtDate = parseLocalDateTimeInput(form.start_at);
  const endAtDate = parseLocalDateTimeInput(form.end_at);
  const isPercentDiscount = form.discount_type === '702';
  const isGenericCoupon = form.usage_type === '801';

  if (!normalizedName) {
    return { errorKey: tPromotion('validation.couponNameRequired') };
  }
  if (!form.usage_type) {
    return { errorKey: tPromotion('validation.usageTypeRequired') };
  }
  if (!form.discount_type) {
    return { errorKey: tPromotion('validation.discountTypeRequired') };
  }
  if (!normalizedValue) {
    return {
      errorKey: isPercentDiscount
        ? tPromotion('validation.valuePercentRequired')
        : tPromotion('validation.valueAmountRequired'),
    };
  }

  const numericValue = Number(normalizedValue);
  if (!Number.isFinite(numericValue)) {
    return {
      errorKey: isPercentDiscount
        ? tPromotion('validation.valuePercentInvalid')
        : tPromotion('validation.valueAmountInvalid'),
    };
  }
  if (isPercentDiscount) {
    if (numericValue <= 0 || numericValue > 100) {
      return { errorKey: tPromotion('validation.valuePercentInvalid') };
    }
  } else if (numericValue <= 0) {
    return { errorKey: tPromotion('validation.valueAmountInvalid') };
  }

  if (isGenericCoupon && !normalizedCode) {
    return { errorKey: tPromotion('validation.codeRequired') };
  }
  if (!normalizedQuantity) {
    return { errorKey: tPromotion('validation.quantityRequired') };
  }
  if (
    !isPositiveIntegerString(normalizedQuantity) ||
    Number(normalizedQuantity) <= 0
  ) {
    return { errorKey: tPromotion('validation.quantityInvalid') };
  }
  if (!normalizedCourseId) {
    return { errorKey: t('module.order.redemptionCodes.courseRequired') };
  }
  if (!form.start_at) {
    return { errorKey: tPromotion('validation.startAtRequired') };
  }
  if (!form.end_at) {
    return { errorKey: tPromotion('validation.endAtRequired') };
  }
  if (
    !startAtDate ||
    !endAtDate ||
    endAtDate.getTime() < startAtDate.getTime()
  ) {
    return { errorKey: tPromotion('validation.endAtInvalid') };
  }

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

  return {
    errorKey: '',
    payload,
    submitSuccessKey: isEditing
      ? t('module.order.redemptionCodes.updateSuccess')
      : t('module.order.redemptionCodes.createSuccess'),
  };
};
