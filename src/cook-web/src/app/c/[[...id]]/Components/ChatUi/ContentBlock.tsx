import { memo, useCallback, useState } from 'react';
import { useLongPress } from 'react-use';
import { isEqual } from 'lodash';
// TODO@XJL
// import ContentRender from '../../../../../../../../../markdown-flow-ui/src/components/ContentRender/ContentRender';
import { ContentRender, type OnSendContentParams } from 'markdown-flow-ui';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import type { ChatContentItem } from './useChatLogicHook';

interface ContentBlockProps {
  item: ChatContentItem;
  mobileStyle: boolean;
  blockBid: string;
  confirmButtonText?: string;
  onClickCustomButtonAfterContent?: (blockBid: string) => void;
  onSend: (content: OnSendContentParams, blockBid: string) => void;
  onLongPress?: (event: any, item: ChatContentItem) => void;
  beforeSend?: (params: OnSendContentParams) => boolean;
}

const ContentBlock = memo(
  ({
    item,
    mobileStyle,
    blockBid,
    confirmButtonText,
    onClickCustomButtonAfterContent,
    onSend,
    onLongPress,
    beforeSend,
  }: ContentBlockProps) => {
    const { t } = useTranslation();
    const [showRegenerateDialog, setShowRegenerateDialog] = useState(false);
    const [pendingSendParams, setPendingSendParams] =
      useState<OnSendContentParams | null>(null);

    const handleClick = useCallback(() => {
      onClickCustomButtonAfterContent?.(blockBid);
    }, [blockBid, onClickCustomButtonAfterContent]);

    const handleLongPress = useCallback(
      (event: any) => {
        if (onLongPress && mobileStyle) {
          onLongPress(event, item);
        }
      },
      [onLongPress, mobileStyle, item],
    );

    const longPressEvent = useLongPress(handleLongPress, {
      isPreventDefault: false,
      delay: 600,
    });

    const _onSend = useCallback(
      (content: OnSendContentParams) => {
        onSend(content, blockBid);
      },
      [onSend, blockBid],
    );

    const handleBeforeSend = useCallback((params: OnSendContentParams) => {
      setPendingSendParams(params);
      setShowRegenerateDialog(true);
      return false;
    }, []);

    const handleConfirm = useCallback(() => {
      if (!pendingSendParams) {
        setShowRegenerateDialog(false);
        return;
      }
      const canProceed = beforeSend ? beforeSend(pendingSendParams) : true;
      if (canProceed) {
        _onSend(pendingSendParams);
      }
      setShowRegenerateDialog(false);
      setPendingSendParams(null);
    }, [_onSend, beforeSend, pendingSendParams]);

    const handleCancel = useCallback(() => {
      setPendingSendParams(null);
      setShowRegenerateDialog(false);
    }, []);

    return (
      <div
        className={cn('content-render-theme', mobileStyle ? 'mobile' : '')}
        {...(mobileStyle ? longPressEvent : {})}
      >
        <ContentRender
          // typingSpeed={20}
          enableTypewriter={false}
          content={item.content || ''}
          onClickCustomButtonAfterContent={handleClick}
          customRenderBar={item.customRenderBar}
          defaultButtonText={item.defaultButtonText}
          defaultInputText={item.defaultInputText}
          defaultSelectedValues={item.defaultSelectedValues}
          readonly={item.readonly}
          confirmButtonText={confirmButtonText}
          onSend={_onSend}
          beforeSend={handleBeforeSend}
        />
        <Dialog
          open={showRegenerateDialog}
          onOpenChange={open => {
            setShowRegenerateDialog(open);
            if (!open) {
              setPendingSendParams(null);
            }
          }}
        >
          <DialogContent className='sm:max-w-md'>
            <DialogHeader>
              <DialogTitle>
                {t('module.chat.regenerateConfirmTitle')}
              </DialogTitle>
              <DialogDescription>
                {t('module.chat.regenerateConfirmDescription')}
              </DialogDescription>
            </DialogHeader>
            <DialogFooter className='flex gap-2 sm:gap-2'>
              <button
                type='button'
                onClick={handleCancel}
                className='px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50'
              >
                {t('common.core.cancel')}
              </button>
              <button
                type='button'
                onClick={handleConfirm}
                className='px-4 py-2 text-sm font-medium text-white bg-primary rounded-md hover:bg-primary-lighter'
              >
                {t('common.core.ok')}
              </button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    );
  },
  (prevProps, nextProps) => {
    // Only re-render if item, mobileStyle, blockBid, or confirmButtonText changes
    return (
      prevProps.item.defaultButtonText === nextProps.item.defaultButtonText &&
      prevProps.item.defaultInputText === nextProps.item.defaultInputText &&
      isEqual(
        prevProps.item.defaultSelectedValues,
        nextProps.item.defaultSelectedValues,
      ) &&
      prevProps.item.readonly === nextProps.item.readonly &&
      prevProps.item.content === nextProps.item.content &&
      prevProps.mobileStyle === nextProps.mobileStyle &&
      prevProps.blockBid === nextProps.blockBid &&
      prevProps.confirmButtonText === nextProps.confirmButtonText
      // prevProps.beforeSend === nextProps.beforeSend
    );
  },
);

ContentBlock.displayName = 'ContentBlock';

export default ContentBlock;
