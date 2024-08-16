import { Avatar } from 'antd';
import PopupModal from 'Components/PopupModal';
import styles from './SettingModal.module.scss';
import classNames from 'classnames';
import { useUserStore } from 'stores/useUserStore.js';
import { Modal } from 'antd';
import { memo } from 'react';

export const SettingModal = ({
  open,
  onClose,
  style,
  onLoginClick = () => {},
  onGoToSetting = () => {},
  className,
}) => {
  const { hasLogin, userInfo, logout } = useUserStore((state) => state);

  const onLogoutClick = async (e) => {
    await Modal.confirm({
      title: '确认退出登录？',
      content: '确认退出登录么',
      onOk: async () => {
        await logout();
        onClose?.(e);
      },
    });
  };
  const avatar = userInfo?.avatar || require('@Assets/newchat/light/user.png');

  const onLoginRowClick = () => {
    if (!hasLogin) {
      onLoginClick?.();
    } else {
      onGoToSetting?.();
    }
  };

  return (
    <>
      <PopupModal
        open={open}
        onClose={onClose}
        wrapStyle={{ ...style }}
        className={className}
      >
        <div className={styles.settingModal}>
          <div
            className={classNames(styles.settingRow, styles.loginRow)}
            onClick={onLoginRowClick}
          >
            <div className={styles.loginLeft}>
              <Avatar src={avatar} size={20} />
              <div className={styles.userName}>
                {hasLogin ? userInfo?.name || '默认名称' : '未登录'}
              </div>
            </div>
            <img className={styles.rowIcon} src={require('@Assets/newchat/light/icon16-edit.png')} alt="" />
          </div>
          <div
            className={styles.settingRow}
            onClick={() => {
            }}
          >
            <div>会员管理</div>
            <img
              className={styles.rowIcon}
              src={require('@Assets/newchat/light/icon16-member.png')}
              alt=""
            />
          </div>
          {hasLogin && (
            <div className={styles.settingRow} onClick={onLogoutClick}>
              <div>退出登录</div>
              <img
                className={styles.rowIcon}
                src={require('@Assets/newchat/light/icon16-member.png')}
                alt=""
              />
            </div>
          )}
        </div>
      </PopupModal>
    </>
  );
};

export default memo(SettingModal);
