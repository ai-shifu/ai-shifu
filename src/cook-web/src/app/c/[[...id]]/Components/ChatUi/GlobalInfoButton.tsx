import styles from './GlobalInfoButton.module.scss';

import clsx from 'clsx';
import { memo, useCallback } from 'react';
import Image from 'next/image';

import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover';
import {
  NavigationMenu,
  NavigationMenuItem,
  NavigationMenuLink,
  NavigationMenuList,
} from "@/components/ui/navigation-menu"
import { Button } from '@/components/ui/button';

import FeedbackModal from '@/app/c/[[...id]]/Components/FeedbackModal/FeedbackModal';
import ShortcutModal from '../ShortcutModal/ShortcutModal';

import { useTranslation } from 'react-i18next';
import { useDisclosture } from '@/c-common/hooks/useDisclosture';

import { useUiLayoutStore } from '@/c-store/useUiLayoutStore';
import { useShallow } from 'zustand/react/shallow';
import { useHotkeys } from 'react-hotkeys-hook';
import { SHORTCUT_IDS, genHotKeyIdentifier } from '@/c-service/shortcut';

import { 
  InfoIcon,
  MailIcon,
  MessageSquareWarningIcon,
  SquareArrowOutUpRightIcon,
  KeyboardIcon,
} from 'lucide-react';

import beianIcon from '@/c-assets/newchat/light/beian.png';

const GlobalInfoButton = ({ className }) => {
  const { t } = useTranslation('translation', { keyPrefix: 'c' });

  const {
    open: feedbackModalOpen,
    onOpen: onFeedbackModalOpen,
    onClose: onFeedbackModalClose,
  } = useDisclosture();

  const {
    open: shortcutModalOpen,
    onOpen: onShortcutModalOpen,
    onClose: onShortcutModalClose,
  } = useDisclosture();

  const {
    open: popoverOpen,
    onClose: onPopoverClose,
    onToggle: onPopoverToggle,
  } = useDisclosture();

  const onContactUsClick = useCallback(() => {
    window.open('https://zhentouai.feishu.cn/share/base/form/shrcnwp8SRl1ghzia4fBG08VYkh', '_blank', 'noopener,noreferrer');
    onPopoverClose();
  }, [onPopoverClose]);

  const menuItems = [
    {
      key: '1',
      label: t('navigation.contactUs'),
      icon: <MailIcon />,
      onClick: onContactUsClick,
    },
    {
      key: '2',
      label: t('navigation.feedbackTitle'),
      icon: <MessageSquareWarningIcon />,
      onClick: () => {
        onFeedbackModalOpen();
        onPopoverClose();
      },
    },
    {
      key: '3',
      label: t('navigation.userAgreement'),
      icon: <SquareArrowOutUpRightIcon />,
      onClick: () => {
        onPopoverClose();
        window.open('/useragreement');
      },
    },
    {
      key: '4',
      label: t('navigation.privacyPolicy'),
      icon: <SquareArrowOutUpRightIcon />,
      onClick: () => {
        onPopoverClose();
        window.open('/privacypolicy');
      },
    },
    {
      key: '5',
      label: t('navigation.shortcut'),
      icon: <KeyboardIcon />,
      onClick: () => {
        onPopoverClose();
        onShortcutModalOpen();
      }
    },
  ];

  const { inMacOs } = useUiLayoutStore(
    useShallow((state) => ({ inMacOs: state.inMacOs }))
  );

  useHotkeys(genHotKeyIdentifier(SHORTCUT_IDS.SHORTCUT, inMacOs), () => {
    onPopoverClose();
    onShortcutModalOpen();
  }, []);

  return (
    <>
      <Popover
        open={popoverOpen}
        onOpenChange={(open) => {
          if (!open) {
            onPopoverClose()
          }
        }}>
      <PopoverContent side='right'>
        <div className={styles.popoverContent}>
            {/* <Menu items={menuItems} selectable={false} /> */}
            <NavigationMenu orientation='vertical'>
              <NavigationMenuList>
                <NavigationMenuItem>
                  {menuItems.map((item) => {
                    return (
                      <NavigationMenuLink key={item.key} asChild>
                        <Button variant='link' onClick={item.onClick}>
                          {item.icon}
                          {item.label}
                        </Button>
                      </NavigationMenuLink>
                    )
                  })}
                </NavigationMenuItem>
              </NavigationMenuList>
            </NavigationMenu>

            <div className={styles.policyInfo}>
              <div className={styles.policyInfoRow}>
                {t('common.companyName')}
              </div>
              <div className={styles.policyInfoRow}>
                {t('common.companyAddress')}
              </div>
              <div className={styles.policyInfoRow}>
                <a
                  className={styles.miitLink}
                  href="https://beian.miit.gov.cn/"
                  target="_blank"
                  rel="noreferrer"
                >
                  {t('navigation.icp')}
                </a>
              </div>
              <div className={clsx(styles.gonganRow, styles.policyInfoRow)}>
                <Image 
                  src={beianIcon.src}
                  width={12}
                  height={14}
                  className={styles.beianIcon}
                  alt={t('navigation.filing')}
                />
                <span>{t('navigation.gongan')}</span>
              </div>
            </div>
          </div>
        </PopoverContent>
        <PopoverTrigger asChild>
          <button
            type="button"
            className={clsx(styles.globalInfoButton, className)}
            onClick={onPopoverToggle}>
            <InfoIcon />
          </button>
        </PopoverTrigger>
      </Popover>

      <FeedbackModal
        open={feedbackModalOpen}
        onClose={() => {
          onFeedbackModalClose();
        }}
      />
      <ShortcutModal
        open={shortcutModalOpen}
        onClose={() => {
          onShortcutModalClose();
        }}
      />
    </>
  );
};

export default memo(GlobalInfoButton);
