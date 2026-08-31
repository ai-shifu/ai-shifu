import React from 'react';
import { Trans, useTranslation } from 'react-i18next';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/AlertDialog';
import type { PromotionStatusChangeTarget } from './promotionPageShared';

const PromotionStatusConfirmDialog = ({
  changeTarget,
  submitting,
  onOpenChange,
  onConfirm,
}: {
  changeTarget: PromotionStatusChangeTarget | null;
  submitting: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => Promise<void>;
}) => {
  const { t } = useTranslation();
  const { t: tPromotion } = useTranslation('module.operationsPromotion');
  const itemName = React.useMemo(() => {
    if (!changeTarget) {
      return '';
    }
    if (changeTarget.entityType === 'coupon') {
      return changeTarget.item.name || changeTarget.item.coupon_bid;
    }
    if (changeTarget.entityType === 'campaign') {
      return changeTarget.item.name || changeTarget.item.promo_bid;
    }
    if (changeTarget.entityType === 'packageCampaign') {
      return changeTarget.item.name || changeTarget.item.campaign_bid;
    }
    return changeTarget.item.campaign_name || changeTarget.item.campaign_bid;
  }, [changeTarget]);

  return (
    <AlertDialog
      open={Boolean(changeTarget)}
      onOpenChange={onOpenChange}
    >
      <AlertDialogContent className='sm:max-w-[440px]'>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {changeTarget?.enabling
              ? tPromotion('messages.enableConfirmTitle')
              : tPromotion('messages.disableConfirmTitle')}
          </AlertDialogTitle>
          <AlertDialogDescription className='text-left text-sm text-muted-foreground'>
            {changeTarget ? (
              <Trans
                ns='module.operationsPromotion'
                i18nKey={
                  changeTarget.enabling
                    ? 'messages.enableConfirmDescription'
                    : 'messages.disableConfirmDescription'
                }
                values={{ name: itemName }}
                components={{
                  strong: <span className='font-semibold text-foreground' />,
                }}
              />
            ) : null}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={submitting}>
            {t('common.core.cancel')}
          </AlertDialogCancel>
          <AlertDialogAction
            disabled={submitting}
            onClick={event => {
              event.preventDefault();
              void onConfirm();
            }}
          >
            {changeTarget?.enabling
              ? tPromotion('actions.confirmEnable')
              : tPromotion('actions.confirmDisable')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
};

export default PromotionStatusConfirmDialog;
