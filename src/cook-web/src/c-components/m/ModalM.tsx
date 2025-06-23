import styels from './ModalM.module.scss';

import { forwardRef, memo } from 'react';
import clsx from 'clsx';

// TODO: FIXME
// import { Modal } from 'antd-mobile';

export const ModalM = forwardRef((props, ref) => {
  return (
    <Modal
      ref={ref}
      showCloseButton={true}
      {...props}
      className={clsx(styels.modalM, props.className)}
    />
  );
});

ModalM.displayName = 'ModalM';

export default memo(ModalM);
