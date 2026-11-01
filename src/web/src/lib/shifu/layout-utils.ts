import { FRAME_LAYOUT_MOBILE } from '@/constants/ui-constants';

const checkMobileStyle = frameLayout => {
  return frameLayout === FRAME_LAYOUT_MOBILE;
};

export const utils = {
  checkMobileStyle,
};
