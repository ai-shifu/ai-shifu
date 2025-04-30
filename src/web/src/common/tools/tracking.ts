export const EVENT_NAMES = {
  VISIT: 'visit',
  TRIAL_PROGRESS: 'trial_progress',
  POP_PAY: 'pop_pay',
  POP_LOGIN: 'pop_login',
  PAY_SUCCEED: 'pay_succeed',
  NAV_BOTTOM_BEIAN: 'nav_bottom_beian',
  NAV_BOTTOM_SKIN: 'nav_bottom_skin',
  NAV_BOTTOM_SETTING: 'nav_bottom_setting',
  NAV_TOP_LOGO: 'nav_top_logo',
  NAV_TOP_EXPAND: 'nav_top_expand',
  NAV_TOP_COLLAPSE: 'nav_top_collapse',
  NAV_SECTION_SWITCH: 'nav_section_switch',
  RESET_CHAPTER: 'reset_chapter',
  RESET_CHAPTER_CONFIRM: 'reset_chapter_confirm',
  USER_MENU: 'user_menu',
  USER_MENU_BASIC_INFO: 'user_menu_basic_info',
  USER_MENU_PERSONALIZED: 'user_menu_personalized',
};

export const tracking = async (eventName, eventData) => {
  try {
    const umami = window.umami;
    // dont track if umami is not loaded
    if (!umami) {
      return;
    }
    umami.track(eventName, eventData);
  } catch (error) {}
};
