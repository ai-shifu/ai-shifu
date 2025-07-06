import styles from './ChatMobileHeader.module.scss';

import { memo } from 'react';
import { cn } from '@/lib/utils'

import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover';

import { Button } from '@/components/ui/button'
import { 
  CircleEllipsisIcon as MoreIcon,
  CircleX as CloseIcon
} from 'lucide-react'

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
    shifu.ControlTypes.MOBILE_HEADER_ICON_POPOVER
  );

  return (
    <div className={cn(styles.ChatMobileHeader, className)}>
      {iconPopoverPayload && (
        <div className="hidden" style={{display: "none"}}>
          <MobileHeaderIconPopover
            payload={iconPopoverPayload}
            onOpen={onIconPopoverOpen}
            onClose={onIconPopoverClose}
          />
        </div>
      )}
      <LogoWithText direction="row" size={30} />
      <Popover open={iconPopoverOpen && hasPopoverContentControl}>
        <PopoverTrigger asChild>
          <Button onClick={onSettingClick}>
            {navOpen ? <CloseIcon /> : <MoreIcon />}
          </Button>
        </PopoverTrigger>
        <PopoverContent className={styles.iconButtonPopover}>
            <MobileHeaderIconPopover
              payload={iconPopoverPayload}
              onOpen={onIconPopoverOpen}
              onClose={onIconPopoverClose}
            />
        </PopoverContent>
      </Popover>
    </div>
  );
};

export default memo(ChatMobileHeader);
