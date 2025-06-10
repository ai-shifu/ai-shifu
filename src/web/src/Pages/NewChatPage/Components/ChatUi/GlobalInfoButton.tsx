import classNames from 'classnames';
import { memo } from 'react';
import { Popover, Menu } from 'antd';
import styles from './GlobalInfoButton.module.scss';
import FeedbackModal from 'Pages/NewChatPage/Components/FeedbackModal/FeedbackModal';
import ShortcutModal from '../ShortcutModal/ShortcutModal';
import MessageIcon from 'Assets/newchat/light/message.png';
import FeedbackIcon from 'Assets/newchat/light/feedback-line.png';
import OpenLinkIcon from 'Assets/newchat/light/open-link.png';
import shotcutIcon from 'Assets/newchat/light/shotcut.png';
import { InfoCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useDisclosture } from 'common/hooks/useDisclosture';
import { useCallback } from 'react';
import { useUiLayoutStore } from 'stores/useUiLayoutStore';
import { useShallow } from 'zustand/react/shallow';
import { useHotkeys } from 'react-hotkeys-hook';
import { SHORTCUT_IDS, genHotKeyIdentifier } from 'Service/shortcut';

const GlobalInfoButton = ({ className }) => {
  const { t } = useTranslation();
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
      icon: <img className={styles.rowIcon} src={MessageIcon} alt="icon" />,
      onClick: onContactUsClick,
    },
    {
      key: '2',
      label: t('navigation.feedbackTitle'),
      icon: <img className={styles.rowIcon} src={FeedbackIcon} alt="icon" />,
      onClick: () => {
        onFeedbackModalOpen();
        onPopoverClose();
      },
    },
    {
      key: '3',
      label: t('navigation.userAgreement'),
      icon: <img className={styles.rowIcon} src={OpenLinkIcon} alt="icon" />,
      onClick: () => {
        onPopoverClose();
        window.open('/useragreement');
      },
    },
    {
      key: '4',
      label: t('navigation.privacyPolicy'),
      icon: <img className={styles.rowIcon} src={OpenLinkIcon} alt="icon" />,
      onClick: () => {
        onPopoverClose();
        window.open('/privacypolicy');
      },
    },
    {
      key: '5',
      label: t('navigation.shortcut'),
      icon: <img className={styles.rowIcon} src={shotcutIcon} alt="icon" />,
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
        onClose={onPopoverClose}
        content={
          <div className={styles.popoverContent}>
            <Menu items={menuItems} selectable={false} />
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
              <div
                className={classNames(styles.gonganRow, styles.policyInfoRow)}
              >
                <img
                  className={styles.beianIcon}
                  src={require('@Assets/newchat/light/beian.png')}
                  alt={t('navigation.filing')}
                />
                <div>{t('navigation.gongan')}</div>
              </div>
            </div>
          </div>
        }
        arrow={false}
        placement="topRight"
      >
        <button
          type="button"
          className={classNames(styles.globalInfoButton, className)}
          onClick={onPopoverToggle}
        >
          <InfoCircleOutlined />
        </button>
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
