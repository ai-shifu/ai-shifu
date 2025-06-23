import { memo, useEffect, useCallback } from 'react';
import { useShallow } from 'zustand/react/shallow';
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover';
import styles from './NavigatorTitleRightArea.module.scss';
import { customEvents, EVENT_TYPE } from '../events/event';
import { shifu } from '../config/config';
import { usePayStore } from '../stores/usePayStore';
import OrderPromotePopoverContent from './OrderPromotePopoverContent';
import ToPayButton from './ToPayButton';
export const ControlType = 'navigator_top_area';

const NavigatorTitleRightArea = ({ payload }) => {
  const {
    hasPay,
    updateHasPay,
    orderPromotePopoverOpen,
    updateOrderPromotePopoverOpen,
  } = usePayStore(
    useShallow((state) => ({
      hasPay: state.hasPay,
      updateHasPay: state.updateHasPay,
      orderPromotePopoverOpen: state.orderPromotePopoverOpen,
      updateOrderPromotePopoverOpen: state.updateOrderPromotePopoverOpen,
    }))
  );

  const { frameLayout } = shifu.stores.useUiLayoutStore(
    useShallow((state) => ({ frameLayout: state.frameLayout }))
  );

  const { trackEvent, EVENT_NAMES } = shifu.hooks.useTracking();

  const onUnlockAllClick = useCallback(() => {
    if (!hasPay) {
      shifu.payTools.openPay({});
      trackEvent(EVENT_NAMES.POP_PAY, { from: 'popconfirm-pay-btn' });
    }
    updateOrderPromotePopoverOpen(false);
  }, [EVENT_NAMES.POP_PAY, hasPay, trackEvent, updateOrderPromotePopoverOpen]);

  const popoverLocation = shifu.utils.checkMobileStyle(frameLayout)
    ? 'bottom'
    : 'rightTop';

  useEffect(() => {
    const onEventHandler = () => {
      updateOrderPromotePopoverOpen(true);
    };

    const onModalOk = () => {
      updateHasPay(true);
    };

    customEvents.addEventListener(
      EVENT_TYPE.NON_BLOCK_PAY_MODAL_CLOSED,
      onEventHandler
    );

    shifu.events.addEventListener(shifu.EventTypes.PAY_MODAL_OK, onModalOk);

    return () => {
      customEvents.removeEventListener(
        EVENT_TYPE.NON_BLOCK_PAY_MODAL_CLOSED,
        onEventHandler
      );
      shifu.events.removeEventListener(
        shifu.EventTypes.PAY_MODAL_OK,
        onModalOk
      );
    };
  }, [updateHasPay, updateOrderPromotePopoverOpen]);

  const onPayButtonClick = useCallback(() => {
    updateOrderPromotePopoverOpen(true);
    trackEvent(EVENT_NAMES.POP_PAY, { from: 'left-nav-top-btn' });
  }, [EVENT_NAMES.POP_PAY, trackEvent, updateOrderPromotePopoverOpen]);

  const onPopoverClose = useCallback(() => {
    updateOrderPromotePopoverOpen(false);
  }, [updateOrderPromotePopoverOpen]);

  return (
    <>
      {!hasPay ? (
        <Popover className={styles.navigatorTitleRightAreaPopover}>
          <PopoverTrigger>
               <ToPayButton onClick={onPayButtonClick}>{payload.title}</ToPayButton>
          </PopoverTrigger>
          <PopoverContent>
          <OrderPromotePopoverContent
              payload={payload}
              onCancelButtonClick={onPopoverClose}
              onOkButtonClick={onUnlockAllClick}
            />
          </PopoverContent>
        </Popover>
      ) : (
        <></>
      )}
    </>
  );
};

export default memo(NavigatorTitleRightArea);
