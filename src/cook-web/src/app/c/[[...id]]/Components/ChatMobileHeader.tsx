import styles from './ChatMobileHeader.module.scss';

import { memo } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { useShallow } from 'zustand/react/shallow';
import { useCourseStore } from '@/c-store';
import { useSystemStore } from '@/c-store/useSystemStore';
import { Avatar, AvatarImage } from '@/components/ui/Avatar';
import { Menu, X } from 'lucide-react';
import MobileHeaderIconPopover from './MobileHeaderIconPopover';
import { useDisclosure } from '@/c-common/hooks/useDisclosure';
import { shifu } from '@/c-service/Shifu';
import {
  getLearningModeShortLabel,
  LEARNING_MODE_OPTIONS,
} from './learningModeOptions';
import HeaderBetaBadge from './HeaderBetaBadge';

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

  const { courseAvatar, courseName } = useCourseStore(
    useShallow(state => ({
      courseAvatar: state.courseAvatar,
      courseName: state.courseName,
    })),
  );
  const { learningMode, showLearningModeToggle, updateLearningMode } =
    useSystemStore(
      useShallow(state => ({
        learningMode: state.learningMode,
        showLearningModeToggle: state.showLearningModeToggle,
        updateLearningMode: state.updateLearningMode,
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
      <div className='flex min-w-0 flex-1 items-center'>
        {courseAvatar ? (
          <Avatar className='mr-2 h-8 w-8 shrink-0'>
            <AvatarImage
              src={courseAvatar}
              alt=''
            />
          </Avatar>
        ) : null}
        <span
          className='min-w-0 truncate text-[16px] font-semibold leading-[14px] text-black/80'
          title={courseName || ''}
        >
          {courseName || ''}
        </span>
      </div>

      <div className={styles.actionGroup}>
        {showLearningModeToggle ? (
          <button
            type='button'
            aria-label={t('module.chat.learningModeToggle')}
            aria-pressed={learningMode === 'listen'}
            className={styles.learningModeSwitch}
            onClick={() =>
              updateLearningMode(learningMode === 'listen' ? 'read' : 'listen')
            }
          >
            {LEARNING_MODE_OPTIONS.map(option => {
              const isActive = learningMode === option.mode;
              const isListenOption = option.mode === 'listen';

              return (
                <span
                  key={option.mode}
                  className={cn(
                    styles.learningModeSwitchButton,
                    isActive ? styles.learningModeSwitchButtonActive : '',
                  )}
                >
                  <span className={styles.learningModeSwitchLabel}>
                    {getLearningModeShortLabel(t, option.mode)}
                  </span>
                  {isListenOption ? (
                    <HeaderBetaBadge
                      variant='inline'
                      className={styles.learningModeBetaBadge}
                    />
                  ) : null}
                </span>
              );
            })}
          </button>
        ) : null}

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
