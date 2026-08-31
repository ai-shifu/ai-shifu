import type { AdminPromotionCouponItem } from '@/app/admin/operations/operation-promotion-types';
import {
  EMPTY_VALUE,
  shouldShowCouponStatusToggle,
} from '@/app/admin/operations/promotions/promotionPageShared';
import { USAGE_PROGRESS_SEPARATOR } from './creatorRedemptionCodeShared';

type TranslationFn = (key: string, options?: Record<string, unknown>) => string;

export const isSingleUseCreatorRedemptionCode = (
  item: AdminPromotionCouponItem,
) => Number(item.usage_type) === 802;

export const getCreatorRedemptionCodeDisplayCode = (
  item: AdminPromotionCouponItem,
) => item.code || EMPTY_VALUE;

export const getCreatorRedemptionUsageProgress = (
  item: AdminPromotionCouponItem,
) =>
  `${String(Number(item.used_count || 0))}${USAGE_PROGRESS_SEPARATOR}${String(
    Number(item.total_count || 0),
  )}`;

export const shouldShowCreatorRedemptionCodesEntry = (
  item: AdminPromotionCouponItem,
) => isSingleUseCreatorRedemptionCode(item);

export const buildCreatorRedemptionRowActions = ({
  item,
  onEdit,
  onExportCodes,
  onToggleStatus,
  tPromotion,
}: {
  item: AdminPromotionCouponItem;
  onEdit: (item: AdminPromotionCouponItem) => void;
  onExportCodes: (item: AdminPromotionCouponItem) => void;
  onToggleStatus: (item: AdminPromotionCouponItem) => void;
  tPromotion: TranslationFn;
}) => [
  {
    key: 'edit',
    label: tPromotion('actions.edit'),
    onClick: () => onEdit(item),
  },
  {
    key: 'export-codes',
    label: tPromotion('actions.exportCodes'),
    hidden: !isSingleUseCreatorRedemptionCode(item),
    onClick: () => onExportCodes(item),
  },
  {
    key: 'toggle-status',
    label:
      item.computed_status === 'inactive'
        ? tPromotion('actions.enable')
        : tPromotion('actions.disable'),
    hidden: !shouldShowCouponStatusToggle(item),
    onClick: () => onToggleStatus(item),
  },
];
