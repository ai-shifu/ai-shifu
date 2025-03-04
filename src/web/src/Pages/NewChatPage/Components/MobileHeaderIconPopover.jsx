import { memo } from 'react';
import { shifu } from 'Service/Shifu.js';

const MobileHeaderIconPopover = ({ payload, onClose, onOpen }) => {
  const Control = shifu.getControl(shifu.ControlTypes.MOBILE_HEADER_ICON_POPOVER);

  return Control && payload ? (
    <div>
      <Control
        payload={payload}
        onClose={onClose}
        onOpen={() => {
          onOpen?.();
        }}
      />
    </div>
  ) : (
    <></>
  );
};

export default memo(MobileHeaderIconPopover);
