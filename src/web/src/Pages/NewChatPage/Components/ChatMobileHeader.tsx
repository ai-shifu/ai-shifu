import { Popover } from 'antd-mobile';
import styles from './ChatMobileHeader.module.scss';
import IconButton from 'Components/IconButton';
import moeIcon from 'Assets/newchat/light/icon16-more2x.png';
import closeIcon from 'Assets/newchat/light/close-2x.png';
import classNames from 'classnames';
import { memo } from 'react';
import LogoWithText from 'Components/logo/LogoWithText';
import MobileHeaderIconPopover from './MobileHeaderIconPopover';
import { useDisclosture } from 'common/hooks/useDisclosture';
import { shifu } from 'Service/Shifu';

export const ChatMobileHeader = ({
  className,
  onSettingClick,
  navOpen,
  iconPopoverPayload,
}) => {
  const {
    open: iconPopoverOpen,
    onOpen: onIconPopoverOpen,
    onClose: onIconPopoverClose,
  } = useDisclosture();

  const hasPopoverContentControl = shifu.hasControl(
    shifu.ControlTypes.MOBILE_HEADER_ICON_POPOVER,
  );

  return (
    <div className={classNames(styles.ChatMobileHeader, className)}>
      {iconPopoverPayload && (
        <div className="hidden" style={{ display: 'none' }}>
          <MobileHeaderIconPopover
            payload={iconPopoverPayload}
            onOpen={onIconPopoverOpen}
          />
        </div>
      )}
      <LogoWithText direction="row" size={30} />
      <Popover
        content={
          <MobileHeaderIconPopover
            payload={iconPopoverPayload}
            onClose={onIconPopoverClose}
          />
        }
        className={styles.iconButtonPopover}
        visible={iconPopoverOpen && hasPopoverContentControl}
        placement="bottom-end"
      >
        <IconButton
          icon={navOpen ? closeIcon : moeIcon}
          onClick={onSettingClick}
        />
      </Popover>
    </div>
  );
};

export default memo(ChatMobileHeader);
