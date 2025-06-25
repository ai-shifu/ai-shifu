import { memo } from 'react';
import styles from './MobileHeaderIconPopoverContent.module.scss';
import { useShallow } from 'zustand/react/shallow';

import { customEvents, EVENT_TYPE } from '../events/event';
import { usePayStore } from '../stores/usePayStore';
import { shifu } from '../config/config';
import OrderPromotePopoverContent from './OrderPromotePopoverContent';
import { useEffect } from 'react';
import { useCallback } from 'react';

const MobileHeaderIconPopoverContent = ({ payload, onClose, onOpen }) => {
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
  // @ts-expect-error EXPECT
  const { trackEvent, EVENT_NAMES } = shifu.hooks.useTracking();

  useEffect(() => {
    if (orderPromotePopoverOpen) {
      onOpen?.();
    } else {
      onClose?.();
    }
  }, [onClose, onOpen, orderPromotePopoverOpen])

  const onOkButtonClick = useCallback(() => {
    if (!hasPay) {
      // @ts-expect-error EXPECT
      shifu.payTools.openPay({});
      trackEvent(EVENT_NAMES.POP_PAY, { from: 'popconfirm-pay-btn' })
    }
    updateOrderPromotePopoverOpen(false);
  }, [EVENT_NAMES.POP_PAY, hasPay, trackEvent, updateOrderPromotePopoverOpen]);

  const onCancelButtonClick = useCallback(() => {
    updateOrderPromotePopoverOpen(false);
    onClose?.();
  }, [onClose, updateOrderPromotePopoverOpen])

  useEffect(() => {
    const onEventHandler = () => {
      updateOrderPromotePopoverOpen(true);
    };

    customEvents.addEventListener(
      EVENT_TYPE.NON_BLOCK_PAY_MODAL_CLOSED,
      onEventHandler
    );

    const onModalOk = () => {
      updateHasPay(true);
    };
    // @ts-expect-error EXPECT
    shifu.events.addEventListener(shifu.EventTypes.PAY_MODAL_OK, onModalOk);

    return () => {
      customEvents.removeEventListener(
        EVENT_TYPE.NON_BLOCK_PAY_MODAL_CLOSED,
        onEventHandler
      );
      // @ts-expect-error EXPECT
      shifu.events.removeEventListener(
        // @ts-expect-error EXPECT
        shifu.EventTypes.PAY_MODAL_OK,
        onModalOk
      );
    };
  }, [onOpen, updateHasPay, updateOrderPromotePopoverOpen]);


  return (
    <>
      <OrderPromotePopoverContent
        payload={payload}
        onCancelButtonClick={onCancelButtonClick}
        onOkButtonClick={onOkButtonClick}
        className={styles.mobileHeaderIconPopoverContent}
      />
    </>
  );
};

export default memo(MobileHeaderIconPopoverContent);
