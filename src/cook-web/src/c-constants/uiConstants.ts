/**
 * Frame layout presets:
 * 1: Separate left and right panels (desktop)
 * 2: Left panel overlays the right panel (tablet)
 * 3: Dense tablet layout
 * 10: Mobile layout
 */
export const FRAME_LAYOUT_PC = 1;
export const FRAME_LAYOUT_PAD = 2;
export const FRAME_LAYOUT_PAD_INTENSIVE = 3;
export const FRAME_LAYOUT_MOBILE = 10;

/**
 * Layout selection is primarily based on the outer container width
 */
export const FRAME_LAYOUT_PC_WIDTH = 1080;
export const FRAME_LAYOUT_PAD_INTENSIVE_WIDTH = 800;
export const FRAME_LAYOUT_MOBILE_WIDTH = 430;

export const calcFrameLayout = selector => {
  if (typeof document === 'undefined') {
    return FRAME_LAYOUT_PC;
  }

  const elem = document.querySelector(selector);
  if (!elem) {
    return FRAME_LAYOUT_PC;
  }

  const w = elem.clientWidth;

  if (w > FRAME_LAYOUT_PC_WIDTH) {
    return FRAME_LAYOUT_PC;
  } else if (w > FRAME_LAYOUT_PAD_INTENSIVE_WIDTH) {
    return FRAME_LAYOUT_PAD;
  } else if (w > FRAME_LAYOUT_MOBILE_WIDTH) {
    return FRAME_LAYOUT_PAD_INTENSIVE;
  } else {
    return FRAME_LAYOUT_MOBILE;
  }
};

/**
 * Theme options
 */
export const THEME_LIGHT = 'light';
export const THEME_DARK = 'dark';

export const inWechat = () => {
  const ua = navigator.userAgent.toLowerCase();
  // @ts-expect-error EXPECT
  const isWXWork = ua.match(/wxwork/i) === 'wxwork';
  const isWeixin = !isWXWork && /MicroMessenger/i.test(ua);

  return isWeixin;
};

// Redirect to the WeChat login flow
export const wechatLogin = ({
  appId,
  redirectUrl = '',
  scope = 'snsapi_base',
  state = '',
}) => {
  const _redirectUrl = encodeURIComponent(redirectUrl || window.location.href);
  const url = `https://open.weixin.qq.com/connect/oauth2/authorize?appid=${appId}&redirect_uri=${_redirectUrl}&response_type=code&scope=${scope}&state=${state}#wechat_redirect`;
  window.location.assign(url);
};

/**
 * Maximum character length for titles (Shifu name, Chapter name, Lesson name)
 */
export const TITLE_MAX_LENGTH = 100;
