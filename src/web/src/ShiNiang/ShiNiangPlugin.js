import { initShifu } from "./config/config.js"
import NonBlockPayControl from "./components/NonBlockPayControl.jsx"
import NavigatorTitleRightArea from "./components/NavigatorTitleRightArea.jsx"
import TrialNodeBottomArea from "./components/TrialNodeBottomArea.jsx";
import MobileHeaderIconPopoverContent from "./components/MobileHeaderIconPopoverContent.jsx";
import ActiveMessage from "./components/ActiveMessage.jsx";

export const shiNiangPlugin = {
  install: (shifu) => {
    initShifu(shifu);
    shifu.registerChatInputActionControls('nonblock_order', NonBlockPayControl);
    shifu.registerControl(shifu.ControlTypes.NAVIGATOR_TITLE_RIGHT_AREA, NavigatorTitleRightArea);
    shifu.registerControl(shifu.ControlTypes.TRIAL_NODE_BOTTOM_AREA, TrialNodeBottomArea);
    shifu.registerControl(shifu.ControlTypes.MOBILE_HEADER_ICON_POPOVER, MobileHeaderIconPopoverContent);
    shifu.registerControl(shifu.ControlTypes.ACTIVE_MESSAGE, ActiveMessage);
  }
}
