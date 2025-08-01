import React, { useState, useEffect, useCallback, useRef } from 'react';
import clsx from 'clsx';
import { Input, InputProps } from '../Input';
import { SendConfirm } from '../SendConfirm';
import riseInput from './riseInput';
import parseDataTransfer from '../../utils/parseDataTransfer';
import canUse from '../../utils/canUse';

const canTouch = canUse('touch');

interface ComposerInputProps extends InputProps {
  invisible: boolean;
  inputRef: React.MutableRefObject<HTMLTextAreaElement>;
  onImageSend?: (file: File) => Promise<any>;
}

export const ComposerInput = ({
  inputRef,
  invisible,
  onImageSend,
  ...rest
}: ComposerInputProps) => {
  const [pastedImage, setPastedImage] = useState<File | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  const handlePaste = useCallback((e: React.ClipboardEvent<any>) => {
    parseDataTransfer(e, setPastedImage);
  }, []);

  const handleImageCancel = useCallback(() => {
    setPastedImage(null);
  }, []);

  const handleImageSend = useCallback(() => {
    if (onImageSend && pastedImage) {
      Promise.resolve(onImageSend(pastedImage)).then(() => {
        setPastedImage(null);
      });
    }
  }, [onImageSend, pastedImage]);

  useEffect(() => {
    if (canTouch && inputRef.current && wrapRef.current) {
      riseInput(inputRef.current, wrapRef.current);
    }
  }, [inputRef]);

  return (
    <div
      className={clsx({ 'S--invisible': invisible })}
      ref={wrapRef}
    >
      <Input
        className='Composer-input'
        rows={1}
        autoSize
        enterKeyHint='send'
        onPaste={onImageSend ? handlePaste : undefined}
        ref={inputRef}
        {...rest}
      />
      {pastedImage && (
        <SendConfirm
          file={pastedImage}
          onCancel={handleImageCancel}
          onSend={handleImageSend}
        />
      )}
    </div>
  );
};
