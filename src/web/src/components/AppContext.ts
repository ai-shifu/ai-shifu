import { createContext } from 'react';
import { THEME_LIGHT, FRAME_LAYOUT_PC } from '@/constants/uiConstants';
import { UserInfo } from '@/types/index';

export const AppContext = createContext<{
  isLoggedIn: boolean;
  mobileStyle: boolean;
  userInfo: UserInfo | null;
  theme: string;
  frameLayout: number;
}>({
  isLoggedIn: false,
  mobileStyle: false,
  userInfo: null,
  theme: THEME_LIGHT,
  frameLayout: FRAME_LAYOUT_PC,
});
