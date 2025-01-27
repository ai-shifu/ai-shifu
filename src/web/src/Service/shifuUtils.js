import { FRAME_LAYOUT_MOBILE } from "constants/uiConstants.js"

const checkMobileStyle = (frameLayout) => {
  return frameLayout === FRAME_LAYOUT_MOBILE
}

export const utils = {
  checkMobileStyle
}
