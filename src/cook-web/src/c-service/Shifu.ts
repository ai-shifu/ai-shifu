import { useUserStore } from '@/c-store/useUserStore';
import { useUiLayoutStore } from '@/c-store/useUiLayoutStore';
import { tokenTool } from './storeUtil';
import { FRAME_LAYOUT_MOBILE } from '@/c-constants/uiConstants';
import { utils } from './shifuUtils';
import { INTERACTION_OUTPUT_TYPE } from '@/c-constants/courseConstants';
import { useTracking } from '@/c-common/hooks/useTracking';

const createShifu = () => {
  const chatInputActionControls = {}
  const controls = {}
  const eventHandlers = new EventTarget();

  const EventTypes = {
    OPEN_LOGIN_MODAL: 'OPEN_LOGIN_MODAL',
    LOGIN_MODAL_CANCEL: 'LOGIN_MODAL_CANCEL',
    LOGIN_MODAL_OK: 'LOGIN_MODAL_OK',
    OPEN_PAY_MODAL: 'OPEN_PAY_MODAL',
    PAY_MODAL_OK: 'PAY_MODAL_OK',
    PAY_MODAL_CANCEL: 'PAY_MODAL_CANCEL',
    RESET_CHAPTER: 'RESET_CHAPTER',
  }

  const ControlTypes = {
    NAVIGATOR_TITLE_RIGHT_AREA: 'NAVIGATOR_TITLE_RIGHT_AREA',
    TRIAL_NODE_BOTTOM_AREA: 'TRIAL_NODE_BOTTOM_AREA',
    MOBILE_HEADER_ICON_POPOVER: 'MOBILE_HEADER_ICON_POPOVER',
    ACTIVE_MESSAGE: 'ACTIVE_MESSAGE',
  }

  const constants = {
    INTERACTION_OUTPUT_TYPE,
  }

  const getConfig = () => {
    return {
      isLogin: useUserStore.getState().isLogin,
      userInfo: useUserStore.getState().userInfo,
      frameLayout: useUiLayoutStore.getState().frameLayout,
      inMobile: useUiLayoutStore.getState().inMobile,
      inWechat: useUiLayoutStore.getState().inWechat,
      token: tokenTool.get(),
      mobileStyle: useUiLayoutStore.getState().frameLayout === FRAME_LAYOUT_MOBILE,
    }
  }

  const registerControl = (type, control) => {
    controls[type] = control;
  }

  const getControl = (type) => {
    return controls[type];
  }

  const hasControl = (type) => {
    return type in controls;
  }

  const registerChatInputActionControls = (type, control) => {
    chatInputActionControls[type] = control;
  }

  const getChatInputActionControls = (type) => {
    return chatInputActionControls[type];
  }

  const hasChatInputActionControls = (type) => {
    return type in chatInputActionControls;
  }

  const loginTools = {
    openLogin: () => {
      eventHandlers.dispatchEvent(new CustomEvent(EventTypes.OPEN_LOGIN_MODAL));
    },
    emitLoginModalCancel: (e) => {
      eventHandlers.dispatchEvent(new CustomEvent(EventTypes.LOGIN_MODAL_CANCEL, { detail: e }));
    },
    emitLoginModalOk: (e) => {
      eventHandlers.dispatchEvent(new CustomEvent(EventTypes.LOGIN_MODAL_OK, { detail: e }));
    }
  }

  const payTools = {
    openPay: ({ type = '', payload = {} }) => {
      eventHandlers.dispatchEvent(new CustomEvent(EventTypes.OPEN_PAY_MODAL, { detail: { type, payload } }));
    },
    emitPayModalCancel: (e) => {
      eventHandlers.dispatchEvent(new CustomEvent(EventTypes.PAY_MODAL_CANCEL, { detail: e }));
    },
    emitPayModalOk: (e) => {
      eventHandlers.dispatchEvent(new CustomEvent(EventTypes.PAY_MODAL_OK, { detail: e }));
    }
  }

  const resetTools = {
    resetChapter: (e) => {
      eventHandlers.dispatchEvent(new CustomEvent(EventTypes.RESET_CHAPTER, { detail: e }));
    }
  }

  const stores = {
    useUserStore,
    useUiLayoutStore,
  }

  const hooks = {
    useTracking,
  }

  const installPlugin = (plugin) => {
    plugin.install({
      stores,
      getConfig,
      ControlTypes,
      EventTypes,
      events: eventHandlers,
      registerChatInputActionControls,
      registerControl,
      loginTools,
      payTools,
      utils,
      constants,
      hooks,
    })
  }

  return {
    stores,
    getConfig,
    ControlTypes,
    EventTypes,
    events: eventHandlers,
    resetTools,
    registerChatInputActionControls,
    registerControl,
    installPlugin,
    getChatInputActionControls,
    hasChatInputActionControls,
    getControl,
    hasControl,
    loginTools,
    payTools,
    utils,
    constants,
    hooks,
  }
}

export const shifu = createShifu();
