import { useState, useEffect, useRef } from 'react';
import styles from './PopupModal.module.scss'

export const PopupModal = ({
  open = false,
  onClose = () => {},
  children,
  style,
  wrapStyle,
}) => {
  const popupRef = useRef(null);

  // 点击其他区域关闭弹出窗口
  const handleClickOutside = (event) => {
    if (popupRef.current && !popupRef.current.contains(event.target)) {
      onClose?.();
    }
  };

  // 监听点击事件
  useEffect(() => {
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  return (
    <div className={styles.popupModalWrapper} style={wrapStyle}>
      {open && <div style={style} className={styles.popupModal} ref={popupRef}>{ children }</div>}
    </div>
  );
}

export default PopupModal;
