import styles from './ChatMobileHeader.module.scss';

import { memo } from 'react';
import { cn } from '@/lib/utils';

import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from '@/components/ui/Popover';
import IconButton from './IconButton/IconButton';
import moeIcon from './IconButton/icon16-more2x.png';
import closeIcon from './IconButton/close-2x.png';

import { Button } from '@/components/ui/Button';
import { MoreHorizontal as MoreIcon, X as CloseIcon } from 'lucide-react';

import MobileHeaderIconPopover from './MobileHeaderIconPopover';
import LogoWithText from '@/c-components/logo/LogoWithText';
import { useDisclosure } from '@/c-common/hooks/useDisclosure';
import { shifu } from '@/c-service/Shifu';

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
  } = useDisclosure();

  const hasPopoverContentControl = shifu.hasControl(
    shifu.ControlTypes.MOBILE_HEADER_ICON_POPOVER,
  );

  const popoverVisible = iconPopoverOpen && hasPopoverContentControl;

  return (
    <div className={cn(styles.ChatMobileHeader, className)}>
      {iconPopoverPayload && (
        <div
          className='hidden'
          style={{ display: 'none' }}
        >
          <MobileHeaderIconPopover
            payload={iconPopoverPayload}
            onOpen={onIconPopoverOpen}
          />
        </div>
      )}
      <LogoWithText
        direction='row'
        size={30}
      />
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
          icon={navOpen ? closeIcon.src : moeIcon.src}
          onClick={onSettingClick}
        />
      </Popover>
    </div>
  );
};

export default memo(ChatMobileHeader);
