import styles from './ChatMobileHeader.module.scss';

import { memo } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { useShallow } from 'zustand/react/shallow';
import { useSystemStore } from '@/c-store/useSystemStore';
import { Menu, X } from 'lucide-react';
import MobileHeaderIconPopover from './MobileHeaderIconPopover';
import { useDisclosure } from '@/c-common/hooks/useDisclosure';
import { shifu } from '@/c-service/Shifu';
import CourseHeaderSummary from './CourseHeaderSummary';
import LearningModeSwitch from './LearningModeSwitch';

export const ChatMobileHeader = ({
  className,
  onSettingClick,
  navOpen,
  iconPopoverPayload,
}) => {
  const { t } = useTranslation();
  const { onOpen: onIconPopoverOpen, onClose: onIconPopoverClose } =
    useDisclosure();

  const hasPopoverContentControl = shifu.hasControl(
    shifu.ControlTypes.MOBILE_HEADER_ICON_POPOVER,
  );

  const { showLearningModeToggle } = useSystemStore(
    useShallow(state => ({
      showLearningModeToggle: state.showLearningModeToggle,
    })),
  );
  const MenuIcon = navOpen ? X : Menu;

  return (
    <div className={cn(styles.ChatMobileHeader, className)}>
      {iconPopoverPayload && hasPopoverContentControl ? (
        <div
          className='hidden'
          style={{ display: 'none' }}
        >
          <MobileHeaderIconPopover
            payload={iconPopoverPayload}
            onOpen={onIconPopoverOpen}
            onClose={onIconPopoverClose}
          />
        </div>
      ) : null}
      <CourseHeaderSummary />

      <div className={styles.actionGroup}>
        {showLearningModeToggle ? <LearningModeSwitch /> : null}

        <button
          type='button'
          aria-label={
            navOpen
              ? t('module.chat.closeCatalog')
              : t('module.chat.openCatalog')
          }
          className={styles.iconButton}
          onClick={onSettingClick}
        >
          <MenuIcon
            size={20}
            strokeWidth={2}
            className='text-neutral-500'
          />
        </button>
      </div>
    </div>
  );
};

export default memo(ChatMobileHeader);
