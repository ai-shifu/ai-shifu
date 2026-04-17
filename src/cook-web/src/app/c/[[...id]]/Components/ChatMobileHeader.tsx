import styles from './ChatMobileHeader.module.scss';

import { memo } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { useShallow } from 'zustand/react/shallow';
import { useCourseStore } from '@/c-store';
import { useSystemStore } from '@/c-store/useSystemStore';
import { Avatar, AvatarImage } from '@/components/ui/Avatar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/DropdownMenu';
import { BookOpen, Check, Headphones, Menu, X } from 'lucide-react';
import MobileHeaderIconPopover from './MobileHeaderIconPopover';
import { useDisclosure } from '@/c-common/hooks/useDisclosure';
import { shifu } from '@/c-service/Shifu';
import {
  getLearningModeLabel,
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
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type='button'
                aria-label={t('module.chat.learningModeToggle')}
                className={cn(styles.iconButton, 'relative overflow-visible')}
              >
                <BookOpen
                  size={20}
                  strokeWidth={2}
                  className='text-neutral-500'
                />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align='end'
              sideOffset={8}
              className='min-w-[120px] rounded-xl border-border bg-white p-1 shadow-lg'
            >
              {LEARNING_MODE_OPTIONS.map(option => {
                const ItemIcon =
                  option.mode === 'listen' ? Headphones : BookOpen;

                return (
                  <DropdownMenuItem
                    key={option.mode}
                    className='rounded-lg px-3 py-2 text-[14px] font-medium text-black/80'
                    onSelect={() => updateLearningMode(option.mode)}
                  >
                    <ItemIcon
                      size={18}
                      strokeWidth={2}
                      className='text-neutral-500'
                    />
                    <span>{getLearningModeLabel(t, option.mode)}</span>
                    {option.mode === 'listen' ? (
                      <HeaderBetaBadge variant='inline' />
                    ) : null}
                    {learningMode === option.mode ? (
                      <Check
                        size={16}
                        strokeWidth={2}
                        className='ml-auto text-black'
                      />
                    ) : null}
                  </DropdownMenuItem>
                );
              })}
            </DropdownMenuContent>
          </DropdownMenu>
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
