import { createContext } from 'react';
import { THEME_LIGHT, FRAME_LAYOUT_PC } from '@constants/uiConstants';

export const AppContext = createContext({
  hasLogin: false,
  mobileStyle: false,
  userInfo: null,
  theme: THEME_LIGHT,
  frameLayout: FRAME_LAYOUT_PC,
});
