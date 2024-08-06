import PopupModal from 'Components/PopupModal';
import { Button } from 'antd';

import styles from './FilingModal.module.scss';
import { memo } from 'react';

export const FillingModal = ({
  open,
  onClose,
  style,
  onFeedbackClick,
  className,
}) => {
  return (
    <PopupModal
      open={open}
      onClose={onClose}
      wrapStyle={{ ...style }}
      className={className}
    >
      <div className={styles.filingModal}>
        <div>北京潺潺山木科技有限公司</div>
        <div>北京朝阳区望京东煌大厦19层163室</div>
        <div>
          <a
            className={styles.miitLink}
            href="https://beian.miit.gov.cn/"
            target="_blank"
            rel="noreferrer"
          >
            京ICP备2024076754号-2
          </a>
        </div>
        <div className={styles.gonganRow}>
          <img
            className={styles.beianIcon}
            src={require('@Assets/newchat/light/beian.png')}
            alt="备案"
          />
          <div>京公网安备11010502055644号</div>
        </div>
        <div className={styles.btnGroup}>
          <Button
            type="link"
            className={styles.actionBtn}
            onClick={onFeedbackClick}
          >
            提交反馈
          </Button>
          <div>|</div>
          <Button
            type="link"
            className={styles.actionBtn}
            onClick={(e) => {
              window.open('/useraggrement');
            }}
          >
            服务协议
          </Button>
          <div>|</div>
          <Button
            type="link"
            className={styles.actionBtn}
            onClick={(e) => {
              window.open('/privacypolicy');
            }}
          >
            隐私政策
          </Button>
        </div>
      </div>
    </PopupModal>
  );
};

export default memo(FillingModal);
