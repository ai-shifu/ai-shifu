import { memo, useEffect, useCallback } from 'react';
import { useShallow } from 'zustand/react/shallow';
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from '@/components/ui/Popover';
import styles from './NavigatorTitleRightArea.module.scss';
import { customEvents, EVENT_TYPE } from '../events/event';
import { shifu } from '../config/config';
import { usePayStore } from '../stores/usePayStore';
import OrderPromotePopoverContent from './OrderPromotePopoverContent';
import ToPayButton from './ToPayButton';
import { useCourseStore } from '@/c-store/useCourseStore';
export const ControlType = 'navigator_top_area';

const NavigatorTitleRightArea = ({ payload }) => {
  const {
    hasPay,
    updateHasPay,
    // orderPromotePopoverOpen,
    updateOrderPromotePopoverOpen,
  } = usePayStore(
    useShallow(state => ({
      hasPay: state.hasPay,
      updateHasPay: state.updateHasPay,
      orderPromotePopoverOpen: state.orderPromotePopoverOpen,
      updateOrderPromotePopoverOpen: state.updateOrderPromotePopoverOpen,
    })),
  );

  // const { frameLayout } = shifu.stores.useUiLayoutStore(
  //   useShallow((state) => ({ frameLayout: state.frameLayout }))
  // );
  // @ts-expect-error EXPECT
  const { trackEvent, EVENT_NAMES } = shifu.hooks.useTracking();

  const { openPayModal, payModalResult } = useCourseStore(
    useShallow(state => ({
      openPayModal: state.openPayModal,
      payModalResult: state.payModalResult,
    })),
  );

  const onUnlockAllClick = useCallback(() => {
    if (!hasPay) {
      openPayModal();
      trackEvent(EVENT_NAMES.POP_PAY, { from: 'popconfirm-pay-btn' });
    }
    updateOrderPromotePopoverOpen(false);
  }, [
    EVENT_NAMES.POP_PAY,
    hasPay,
    openPayModal,
    trackEvent,
    updateOrderPromotePopoverOpen,
  ]);

  // const popoverLocation = shifu.utils.checkMobileStyle(frameLayout)
  //   ? 'bottom'
  //   : 'rightTop';

  useEffect(() => {
    const onEventHandler = () => {
      updateOrderPromotePopoverOpen(true);
    };

    customEvents.addEventListener(
      EVENT_TYPE.NON_BLOCK_PAY_MODAL_CLOSED,
      onEventHandler,
    );

    return () => {
      customEvents.removeEventListener(
        EVENT_TYPE.NON_BLOCK_PAY_MODAL_CLOSED,
        onEventHandler,
      );
    };
  }, [updateOrderPromotePopoverOpen]);

  useEffect(() => {
    if (payModalResult === 'ok') {
      updateHasPay(true);
    }
  }, [payModalResult, updateHasPay]);

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
        <Popover>
          <PopoverTrigger>
            <ToPayButton onClick={onPayButtonClick}>
              {payload.title}
            </ToPayButton>
          </PopoverTrigger>
          <PopoverContent className={styles.navigatorTitleRightAreaPopover}>
            {/* @ts-expect-error EXPECT */}
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
