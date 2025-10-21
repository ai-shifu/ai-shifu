/*
 * Left-hand navigation container
 */
import styles from './NavDrawer.module.scss';
import {
  useContext,
  useState,
  useRef,
  memo,
  useCallback,
  useEffect,
} from 'react';
import clsx from 'clsx';

import { AppContext } from '../AppContext';
import NavHeader from './NavHeader';
import NavBody from './NavBody';
import NavFooter from './NavFooter';
import CourseCatalogList from '../CourseCatalog/CourseCatalogList';

import FeedbackModal from '../FeedbackModal/FeedbackModal';
import { useTracking, EVENT_NAMES } from '@/c-common/hooks/useTracking';
import { getBoolEnv } from '@/c-utils/envUtils';
import { useEnvStore } from '@/c-store/envStore';
import {
  FRAME_LAYOUT_PAD,
  FRAME_LAYOUT_PAD_INTENSIVE,
  FRAME_LAYOUT_MOBILE,
} from '@/c-constants/uiConstants';
import { useDisclosure } from '@/c-common/hooks/useDisclosure';
import MainMenuModal from './MainMenuModal';

import { useUserStore } from '@/store';
import { useUiLayoutStore } from '@/c-store/useUiLayoutStore';
/**
 * Navigation display modes
 * 0: Default, rendered in-flow
 * 1: Rendered as a drawer
 */
export const NAV_SHOW_TYPE_NORMAL = 0;
export const NAV_SHOW_TYPE_DRAWER = 1;

/**
 * Popup window states
 */
export const POPUP_WINDOW_STATE_CLOSE = 0;
export const POPUP_WINDOW_STATE_THEME = 2;
export const POPUP_WINDOW_STATE_SETTING = 3;
export const POPUP_WINDOW_STATE_FILING = 1;

const NAV_DRAWER_MAX_WIDTH = '280px';
const NAV_DRAWER_COLLAPSE_WIDTH = '60px';

const calcNavWidth = frameLayout => {
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
  const isLoggedIn = useUserStore(state => state.isLoggedIn);
  const [delayedIsLoggedIn, setDelayedIsLoggedIn] = useState(isLoggedIn);

  const [isCollapse, setIsCollapse] = useState(false);

  const [bodyScrollTop, setBodyScrollTop] = useState(0);
  const { trackEvent } = useTracking();
  const { frameLayout } = useUiLayoutStore(state => state);

  const { mobileStyle } = useContext(AppContext);
  const alwaysShowLessonTree = useEnvStore(state => state.alwaysShowLessonTree);

  const [feedbackModalOpen, setFeedbackModalOpen] = useState(false);
  // const alwaysShowLessonTree = getBoolEnv('alwaysShowLessonTree');
  const footerRef = useRef(null);
  const bodyRef = useRef(null);

  const {
    open: mainModalOpen,
    onToggle: onMainModalToggle,
    onClose: onMainModalClose,
  } = useDisclosure();

  const onBodyScroll = e => {
    setBodyScrollTop(e.target.scrollTop);
  };

  const onHeaderToggleClick = useCallback(({ isCollapse }) => {
    setIsCollapse(isCollapse);
  }, []);

  const popupWindowClassname = useCallback(() => {
    return isCollapse ? styles.popUpWindowCollapse : styles.popUpWindowExpand;
  }, [isCollapse]);

  const mainModalCloseHandler = useCallback(
    e => {
      // @ts-expect-error EXPECT
      if (footerRef.current && footerRef.current.containElement(e.target)) {
        return;
      }
      onMainModalClose();
    },
    [onMainModalClose],
  );

  // BUGFIX: Smooth out visual flash when login state changes
  // Issue: Switching between logged-in and logged-out states caused a noticeable flash in the navigation
  // Fix: Add a 100ms delayed update so the transition is smoother and visual jumps are reduced
  // Scenario: Especially after logout, avoid the flash between the login button and course list
  useEffect(() => {
    if (isLoggedIn !== delayedIsLoggedIn) {
      const timer = setTimeout(() => {
        setDelayedIsLoggedIn(isLoggedIn);
      }, 100); // 100ms delay
      return () => clearTimeout(timer);
    }
  }, [isLoggedIn, delayedIsLoggedIn]);

  const onFooterClick = useCallback(() => {
    onMainModalToggle();
    trackEvent(EVENT_NAMES.USER_MENU, {
      status: isLoggedIn ? 'logged_in' : 'logged_out',
    });
  }, [isLoggedIn, onMainModalToggle, trackEvent]);

  return (
    <div
      className={clsx(
        styles.navDrawerWrapper,
        frameLayout === FRAME_LAYOUT_MOBILE ? styles.mobile : '',
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
            {!isCollapse &&
              (delayedIsLoggedIn || alwaysShowLessonTree ? (
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
          mobileStyle={frameLayout === FRAME_LAYOUT_MOBILE}
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
