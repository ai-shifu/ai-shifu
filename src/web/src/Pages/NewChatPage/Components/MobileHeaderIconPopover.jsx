import { useEffect, memo } from 'react';
import { shifu } from 'Service/Shifu.js';

const MobileHeaderIconPopover = ({ payload, onClose, onOpen }) => {
  const Control = shifu.getControl(shifu.ControlTypes.MOBILE_HEADER_ICON_POPOVER);

  useEffect(() => {
    console.log('icon popover render');

    return () => {
      console.log('icon popover unmount');
    };
  });

  return Control && payload ? (
    <div>
      <Control
        payload={payload}
        onClose={onClose}
        onOpen={() => {
          console.log('icon popover open');
          onOpen?.();
        }}
      />
    </div>
  ) : (
    <></>
  );
};

export default memo(MobileHeaderIconPopover);
