import styles from './ChatMobileHeader.module.scss';

import { memo } from 'react';
import { cn } from '@/lib/utils';

import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from '@/components/ui/Popover';

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
        open={popoverVisible}
        onOpenChange={next => {
          if (!next) {
            onIconPopoverClose();
          }
        }}
      >
        <PopoverTrigger asChild>
          <Button
            variant='ghost'
            size='icon'
            className='h-9 w-9 rounded-full border border-black/5 bg-white/80 text-slate-600 shadow-sm backdrop-blur'
            onClick={onSettingClick}
            aria-label={navOpen ? 'Close navigation' : 'Open navigation'}
          >
            {navOpen ? (
              <CloseIcon className='h-5 w-5' />
            ) : (
              <MoreIcon className='h-5 w-5' />
            )}
          </Button>
        </PopoverTrigger>
        {iconPopoverPayload && (
          <PopoverContent
            className={cn(styles.iconButtonPopover, 'border-none bg-transparent p-0 shadow-none')}
            align='end'
            side='bottom'
          >
            <MobileHeaderIconPopover
              payload={iconPopoverPayload}
              onOpen={onIconPopoverOpen}
              onClose={onIconPopoverClose}
            />
          </PopoverContent>
        )}
      </Popover>
    </div>
  );
};

export default memo(ChatMobileHeader);
