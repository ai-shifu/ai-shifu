import { Modal } from 'antd-mobile';
import styels from './ModalM.module.scss';
import classNames from 'classnames';
import { forwardRef, memo } from 'react';

export const ModalM = forwardRef((props, ref) => {
  return (
    <Modal
      ref={ref}
      showCloseButton={true}
      {...props}
      className={classNames(styels.modalM, props.className)}
    />
  );
});

export default memo(ModalM);
