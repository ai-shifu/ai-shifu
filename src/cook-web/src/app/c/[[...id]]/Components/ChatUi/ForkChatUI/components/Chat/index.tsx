import React, { useEffect } from 'react';
import { LocaleProvider } from '../LocaleProvider';
import { Navbar, NavbarProps } from '../Navbar';
import {
  MessageContainer,
  MessageContainerProps,
  MessageContainerHandle,
} from '../MessageContainer';
import { QuickReplies, QuickReplyItemProps } from '../QuickReplies';
import {
  Composer as DComposer,
  ComposerProps,
  ComposerHandle,
} from '../Composer';
import isSafari from '../../utils/isSafari';

export type ChatProps = Omit<ComposerProps, 'onFocus' | 'onChange' | 'onBlur'> &
  MessageContainerProps & {
    /**
     * Breakpoint for wide layout mode
     */
    // wideBreakpoint?: string;
    /**
     * Current locale
     */
    locale?: string;
    /**
     * Locale definitions
     */
    locales?: any; // FIXME
    /**
     * Navbar configuration
     */
    navbar?: NavbarProps;
    /**
     * Custom navbar render function
     */
    renderNavbar?: () => React.ReactNode;
    /**
     * Copy for the "load more" section
     */
    // loadMoreText?: string;
    /**
     * Renderer placed above the message list
     */
    // renderBeforeMessageList?: () => React.ReactNode;
    /**
     * Ref to the message list
     */
    messagesRef?: React.RefObject<MessageContainerHandle>;
    /**
     * Pull-to-refresh callback
     */
    // onRefresh?: () => Promise<any>;
    /**
     * Scroll callback for the message list
     */
    // onScroll?: (event: React.UIEvent<HTMLDivElement, UIEvent>) => void;
    /**
     * Messages array
     */
    // messages: MessageProps[];
    /**
     * Renderer for message content
     */
    // renderMessageContent: (message: MessageProps) => React.ReactNode;
    /**
     * Quick reply items
     */
    quickReplies?: QuickReplyItemProps[];
    /**
     * Whether quick replies are visible
     */
    quickRepliesVisible?: boolean;
    /**
     * Quick reply click handler
     */
    onQuickReplyClick?: (item: QuickReplyItemProps, index: number) => void;
    /**
     * Quick reply scroll handler
     */
    onQuickReplyScroll?: () => void;
    /**
     * Renderer for quick replies
     */
    renderQuickReplies?: () => void;
    /**
     * Ref to the composer area
     */
    composerRef?: React.RefObject<ComposerHandle>;
    /**
     * Initial composer text
     */
    // text?: string;
    /**
     * Composer placeholder
     */
    // placeholder?: string;
    /**
     * Composer focus callback
     */
    onInputFocus?: ComposerProps['onFocus'];
    /**
     * Composer change callback
     */
    onInputChange?: ComposerProps['onChange'];
    /**
     * Composer blur callback
     */
    onInputBlur?: ComposerProps['onBlur'];
    /**
     * Send message callback
     */
    // onSend: (type: string, content: string) => void;
    /**
     * Send image callback
     */
    // onImageSend?: (file: File) => Promise<any>;
    /**
     * Input type
     */
    // inputType?: InputType;
    /**
     * Input type switch callback
     */
    // onInputTypeChange?: () => void;
    /**
     * Voice input
     */
    // recorder?: RecorderProps;
    /**
     * Toolbar items
     */
    // toolbar?: ToolbarItemProps[];
    /**
     * Toolbar click callback
     */
    // onToolbarClick?: () => void;
    /**
     * Accessory toggle callback
     */
    // onAccessoryToggle?: () => void;
    /**
     * Custom composer component
     */
    Composer?: React.ElementType; // FIXME
  };

export const Chat = React.forwardRef<HTMLDivElement, ChatProps>(
  (props, ref) => {
    const {
      wideBreakpoint,
      locale = 'zh-CN',
      locales,
      navbar,
      renderNavbar,
      loadMoreText,
      renderBeforeMessageList,
      messagesRef,
      onRefresh,
      onScroll,
      messages = [],
      renderMessageContent,
      onBackBottomShow,
      onBackBottomClick,
      quickReplies = [],
      quickRepliesVisible,
      onQuickReplyClick = () => {},
      onQuickReplyScroll,
      renderQuickReplies,
      text,
      placeholder,
      onInputFocus,
      onInputChange,
      onInputBlur,
      onSend,
      onImageSend,
      inputOptions,
      composerRef,
      inputType,
      onInputTypeChange,
      recorder,
      toolbar,
      onToolbarClick,
      onAccessoryToggle,
      rightAction,
      Composer = DComposer,
    } = props;

    function handleInputFocus(e: React.FocusEvent<HTMLTextAreaElement>) {
      if (messagesRef && messagesRef.current) {
        messagesRef.current.scrollToEnd({ animated: false, force: true });
      }
      if (onInputFocus) {
        onInputFocus(e);
      }
    }

    useEffect(() => {
      if (isSafari()) {
        document.documentElement.dataset.safari = '';
      }
    }, []);

    return (
      // @ts-expect-error EXPECT
      <LocaleProvider
        locale={locale}
        locales={locales}
      >
        <div
          className='ChatApp'
          ref={ref}
        >
          {renderNavbar ? renderNavbar() : navbar && <Navbar {...navbar} />}
          <MessageContainer
            ref={messagesRef}
            loadMoreText={loadMoreText}
            messages={messages}
            renderBeforeMessageList={renderBeforeMessageList}
            renderMessageContent={renderMessageContent}
            onRefresh={onRefresh}
            onScroll={onScroll}
            onBackBottomShow={onBackBottomShow}
            onBackBottomClick={onBackBottomClick}
          />
          <div className='ChatFooter'>
            {renderQuickReplies && renderQuickReplies() ? (
              <QuickReplies
                items={quickReplies}
                visible={quickRepliesVisible}
                onClick={onQuickReplyClick}
                onScroll={onQuickReplyScroll}
              />
            ) : null}
            <Composer
              wideBreakpoint={wideBreakpoint}
              ref={composerRef}
              inputType={inputType}
              text={text}
              inputOptions={inputOptions}
              placeholder={placeholder}
              onAccessoryToggle={onAccessoryToggle}
              recorder={recorder}
              toolbar={toolbar}
              onToolbarClick={onToolbarClick}
              onInputTypeChange={onInputTypeChange}
              onFocus={handleInputFocus}
              onChange={onInputChange}
              onBlur={onInputBlur}
              onSend={onSend}
              onImageSend={onImageSend}
              rightAction={rightAction}
            />
          </div>
        </div>
      </LocaleProvider>
    );
  },
);

Chat.displayName = 'Chat';
