import i18n from 'i18next';
import { ToastAction } from '@/components/ui/Toast';
import { toastOnce } from '@/hooks/useToast';
import { BILLING_PACKAGES_HREF } from './billingNavigation';

export const CREDIT_INSUFFICIENT_BUSINESS_CODE = 7101;
export const DEBUG_DISABLED_BY_SOFTLIMIT_BUSINESS_CODE = 7125;

export type CreditInsufficientAudience =
  | 'learner'
  | 'teacher'
  | 'teacher-collaborator';

export const resolveCourseCreditInsufficientAudience = ({
  previewMode,
  isCurrentUserCourseOwner,
}: {
  previewMode: boolean;
  isCurrentUserCourseOwner: boolean;
}): CreditInsufficientAudience => {
  if (!previewMode) {
    return 'learner';
  }
  return isCurrentUserCourseOwner ? 'teacher' : 'teacher-collaborator';
};

const CREDIT_ERROR_CODES = new Set([
  CREDIT_INSUFFICIENT_BUSINESS_CODE,
  DEBUG_DISABLED_BY_SOFTLIMIT_BUSINESS_CODE,
]);

export const isCreditInsufficientBusinessCode = (
  code?: number,
): code is number => typeof code === 'number' && CREDIT_ERROR_CODES.has(code);

const resolveCreditInsufficientMessageKey = (
  code: number,
  audience: CreditInsufficientAudience,
) => {
  if (audience === 'learner') {
    return 'module.billing.creditInsufficient.learner';
  }
  if (audience === 'teacher-collaborator') {
    return 'module.billing.creditInsufficient.teacherCollaborator';
  }
  if (code === DEBUG_DISABLED_BY_SOFTLIMIT_BUSINESS_CODE) {
    return 'module.billing.creditInsufficient.teacherSoftlimit';
  }
  return 'module.billing.creditInsufficient.teacher';
};

export const getCreditInsufficientMessage = (
  audience: CreditInsufficientAudience,
  code: number,
) => i18n.t(resolveCreditInsufficientMessageKey(code, audience));

export const showCreditInsufficientToast = ({
  audience,
  code,
}: {
  audience: CreditInsufficientAudience;
  code: number;
}) => {
  if (!isCreditInsufficientBusinessCode(code)) {
    return false;
  }

  toastOnce({
    dedupeKey: `credit-insufficient:${audience}:${code}`,
    dedupeWindowMs: Number.POSITIVE_INFINITY,
    title: getCreditInsufficientMessage(audience, code),
    variant: 'destructive',
    duration: 0,
    dismissOnNavigation: true,
    action:
      audience === 'teacher' ? (
        <ToastAction
          altText={i18n.t(
            'module.billing.creditInsufficient.purchaseActionAltText',
          )}
          asChild
        >
          <a href={BILLING_PACKAGES_HREF}>
            {i18n.t('module.billing.alerts.actions.checkoutTopup')}
          </a>
        </ToastAction>
      ) : undefined,
  });
  return true;
};
