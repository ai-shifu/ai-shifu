import { memo, useCallback } from 'react';
import AskButtonInner from './AskButtonInner';
import { shifu } from 'Service/Shifu';
import { useShallow } from 'zustand/react/shallow';
import { useUiLayoutStore } from 'stores/useUiLayoutStore';
import { useHotkeys } from 'react-hotkeys-hook';
import { SHORTCUT_IDS, genHotKeyIdentifier } from 'Service/shortcut';

const AskButton = ({
  className,
  disabled = false,
  total = 0,
  used = 0,
  onClick = () => {},
}) => {
  const isNoLimited = useCallback(() => {
    return used >= total;
  }, [total, used]);

  const buttonClick = useCallback(() => {
    if (isNoLimited()) {
      shifu.payTools.openPay({});
      return;
    }

    if (disabled) {
      return;
    }

    onClick?.();
  }, [disabled, isNoLimited, onClick]);

  const { inMacOs } = useUiLayoutStore(
    useShallow((state) => ({ inMacOs: state.inMacOs }))
  );

  useHotkeys(
    genHotKeyIdentifier(SHORTCUT_IDS.ASK, inMacOs),
    () => {
      buttonClick();
    },
    [buttonClick]
  );

  return (
    <AskButtonInner
      className={className}
      disabled={disabled && !isNoLimited()}
      grayColor={isNoLimited()}
      onClick={buttonClick}
    />
  );
};

export default memo(AskButton);
