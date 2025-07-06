/*
 * 左侧导航控件容器
 */
import styles from './NavDrawer.module.scss';
import { useContext, useState, useRef, memo, useCallback } from 'react';
import clsx from 'clsx';

import { AppContext } from '@/c-components/AppContext';
import NavHeader from './NavHeader';
import NavBody from './NavBody';
import NavFooter from './NavFooter';
import CourseCatalogList from '../CourseCatalog/CourseCatalogList';

import FeedbackModal from '../FeedbackModal/FeedbackModal';
import { useTracking, EVENT_NAMES } from '@/c-common/hooks/useTracking';
import { getBoolEnv } from '@/c-utils/envUtils';
import {
  FRAME_LAYOUT_PAD,
  FRAME_LAYOUT_PAD_INTENSIVE,
  FRAME_LAYOUT_MOBILE,
} from '@/c-constants/uiConstants';
import { useDisclosure } from '@/c-common/hooks/useDisclosure';
import MainMenuModal from './MainMenuModal';

import { useUserStore } from '@/c-store';

/**
 * 导航栏展示形式
 * 0: 默认，在 dom 流中展示
 * 1：作为抽屉展示
 */
export const NAV_SHOW_TYPE_NORMAL = 0;
export const NAV_SHOW_TYPE_DRAWER = 1;

/**
 * 小窗口状态
 */
export const POPUP_WINDOW_STATE_CLOSE = 0;
export const POPUP_WINDOW_STATE_THEME = 2;
export const POPUP_WINDOW_STATE_SETTING = 3;
export const POPUP_WINDOW_STATE_FILING = 1;

const NAV_DRAWER_MAX_WIDTH = '280px';
const NAV_DRAWER_COLLAPSE_WIDTH = '60px';

const calcNavWidth = (frameLayout) => {
  if (frameLayout === FRAME_LAYOUT_MOBILE) {
    return '100%';
  }
  if (frameLayout === FRAME_LAYOUT_PAD_INTENSIVE) {
    return NAV_DRAWER_MAX_WIDTH;
  }
  if (frameLayout === FRAME_LAYOUT_PAD) {
    return '25%';
  }
  return NAV_DRAWER_MAX_WIDTH;
};

const COLLAPSE_WIDTH = NAV_DRAWER_COLLAPSE_WIDTH;

const NavDrawer = ({
  // showType = NAV_SHOW_TYPE_NORMAL,
  courseName = '',
  onLoginClick = () => {},
  lessonTree,
  selectedLessonId = '',
  onChapterCollapse,
  onLessonSelect,
  onTryLessonSelect,
  onBasicInfoClick,
  onPersonalInfoClick,
}) => {
  const userInfo = useUserStore((state) => state.profile);
  const hasLogin = !!userInfo

  const [isCollapse, setIsCollapse] = useState(false);

  const [bodyScrollTop, setBodyScrollTop] = useState(0);
  const { trackEvent } = useTracking();
  const { frameLayout, mobileStyle } = useContext(AppContext);

  const [feedbackModalOpen, setFeedbackModalOpen] = useState(false);
  const alwaysShowLessonTree = getBoolEnv('alwaysShowLessonTree');
  const footerRef = useRef(null);
  const bodyRef = useRef(null);

  const {
    open: mainModalOpen,
    onToggle: onMainModalToggle,
    onClose: onMainModalClose,
  } = useDisclosure();

  const onBodyScroll = (e) => {
    setBodyScrollTop(e.target.scrollTop);
  };

  const onHeaderToggleClick = useCallback(({ isCollapse }) => {
    setIsCollapse(isCollapse);
  }, []);

  const popupWindowClassname = useCallback(() => {
    return isCollapse ? styles.popUpWindowCollapse : styles.popUpWindowExpand;
  }, [isCollapse]);

  const mainModalCloseHandler = useCallback(
    (e) => {
      // @ts-expect-error EXPECT
      if (footerRef.current && footerRef.current.containElement(e.target)) {
        return;
      }
      onMainModalClose();
    },
    [onMainModalClose]
  );

  const onFooterClick = useCallback(() => {
    onMainModalToggle();
    trackEvent(EVENT_NAMES.USER_MENU, {
      status: hasLogin ? 'logged_in' : 'logged_out',
    });
  }, [hasLogin, onMainModalToggle, trackEvent]);

  return (
    <div
      className={clsx(
        styles.navDrawerWrapper,
        mobileStyle ? styles.mobile : ''
      )}
      style={{ width: isCollapse ? COLLAPSE_WIDTH : calcNavWidth(frameLayout) }}
    >
      <div className={styles.navDrawer}>
        <NavHeader
          className={styles.navHeader}
          onToggle={onHeaderToggleClick}
          isCollapse={isCollapse}
          mobileStyle={mobileStyle}
        />

        <div className={styles.bodyWrapper}>
          <div
            className={styles.lessonTreeWrapper}
            onScroll={onBodyScroll}
            ref={bodyRef}
          >
            {!isCollapse && (hasLogin || alwaysShowLessonTree ? (
                <CourseCatalogList
                  courseName={courseName}
                  selectedLessonId={selectedLessonId}
                  catalogs={lessonTree?.catalogs || []}
                  // @ts-expect-error EXPECT
                  catalogCount={lessonTree?.catalogCount || 0}
                  lessonCount={lessonTree?.lessonCount || 0}
                  onChapterCollapse={onChapterCollapse}
                  onLessonSelect={onLessonSelect}
                  onTryLessonSelect={onTryLessonSelect}
                  containerScrollTop={bodyScrollTop}
                  // @ts-expect-error EXPECT
                  containerHeight={bodyRef.current?.clientHeight || 0}
                  bannerInfo={lessonTree?.bannerInfo}
                />
              ) : (
                <NavBody onLoginClick={onLoginClick} />
              ))}
          </div>
        </div>
        <NavFooter
          ref={footerRef}
          // @ts-expect-error EXPECT
          isCollapse={isCollapse}
          onClick={onFooterClick}
        />
        <MainMenuModal
          open={mainModalOpen}
          // @ts-expect-error EXPECT
          onClose={mainModalCloseHandler}
          className={popupWindowClassname()}
          mobileStyle={mobileStyle}
          onBasicInfoClick={onBasicInfoClick}
          onPersonalInfoClick={onPersonalInfoClick}
        />
        <FeedbackModal
          open={feedbackModalOpen}
          onClose={() => {
            setFeedbackModalOpen(false);
          }}
        />
      </div>
    </div>
  );
};

export default memo(NavDrawer);
