import { createContext } from "react";
import { THEME_LIGHT, FRAME_LAYOUT_PC } from '@/c-constants/uiConstants';

export const AppContext = createContext({
  isLoggedIn: false,
  mobileStyle: false,
  userInfo: null,
  theme: THEME_LIGHT,
  frameLayout: FRAME_LAYOUT_PC,
});
