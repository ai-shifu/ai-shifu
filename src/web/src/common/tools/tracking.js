export const EVENT_NAMES = {
  VISIT: 'visit',
  TRIAL_PROGRESS: 'trial_progress',
  POP_PAY: 'pop_pay',
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
}

export const tracking = async (eventName, eventData) => {
  try {
    const umami = window.umami;
    // tracking 库不存在就不处理
    if (!umami) {
      return
    }
    umami.track(eventName, eventData);
  } catch (error) { }
};
