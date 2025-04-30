import { useEffect, useRef } from 'react';
import classNames from 'classnames';
import styles from './PopupModal.module.scss';
import { useCallback } from 'react';

export const PopupModal = ({
  open = false,
  onClose = (event) => {},
  children,
  style,
  wrapStyle,
  className,
}) => {
  const popupRef = useRef(null);

  // 点击其他区域关闭弹出窗口
  const handleClickOutside = useCallback(
    (event) => {
      if (popupRef.current && !popupRef.current.contains(event.target)) {
        onClose?.(event);
      }
    },
    [onClose],
  );

  // 监听点击事件
  useEffect(() => {
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [handleClickOutside]);

  return (
    <div
      className={classNames(styles.popupModalWrapper, className)}
      style={wrapStyle}
    >
      {open && (
        <div style={style} className={styles.popupModal} ref={popupRef}>
          {children}
        </div>
      )}
    </div>
  );
};

export default PopupModal;
