import { useCallback, useState } from 'react';
import { smoothScroll } from 'Utils/smoothScroll';

const SCROLL_BOTTOM_THROTTLE = 50;

// take scoll logic in the separte file
export const useChatComponentsScroll = ({
  chatRef,
  containerStyle,
  messages,
  deleteMsg,
  appendMsg,
}) => {
  const [autoScroll, setAutoScroll] = useState(true);

  const startAutoScroll = useCallback(() => {
    setAutoScroll(true);
    if (messages.length && messages[messages.length - 1].position === 'pop') {
      deleteMsg(messages[messages.length - 1]._id);
    }
  }, [deleteMsg, messages]);

  const stopAutoScroll = useCallback(() => {
    setAutoScroll(false);
    if (messages.length && messages[messages.length - 1].position === 'pop') {
      return;
    }
    appendMsg({ type: 'loading', position: 'pop' });
  }, [appendMsg, messages]);

  const onMessageListScroll = useCallback(
    (e) => {
      const scrollWrapper = e.target;
      const inner = scrollWrapper.children[0];

      if (!scrollWrapper || !inner) {
        return;
      }

      if (
        scrollWrapper.scrollTop >= 0 &&
        scrollWrapper.scrollTop + scrollWrapper.clientHeight <
          inner.clientHeight - SCROLL_BOTTOM_THROTTLE
      ) {
        stopAutoScroll();
      } else {
        startAutoScroll();
      }
    },
    [startAutoScroll, stopAutoScroll],
  );

  const scrollTo = useCallback(
    (height, stopScroll = false) => {
      if (stopScroll) {
        stopAutoScroll();
      }

      const wrapper = chatRef.current?.querySelector(
        `.${containerStyle} .PullToRefresh`,
      );

      if (!wrapper) {
        return;
      }
      smoothScroll({ el: wrapper, to: height });
    },
    [chatRef, containerStyle, stopAutoScroll],
  );

  const scrollToLesson = useCallback(
    (lessonId) => {
      if (!chatRef.current) {
        return;
      }

      const lessonNode = chatRef.current.querySelector(
        `[data-id=lesson-${lessonId}]`,
      );
      if (!lessonNode) {
        return;
      }

      scrollTo(lessonNode.offsetTop, true);
    },
    [chatRef, scrollTo],
  );

  const scrollToBottom = useCallback(() => {
    const inner = chatRef.current?.querySelector(
      `.${containerStyle} .PullToRefresh-inner`,
    );

    if (!inner) {
      return;
    }

    scrollTo(inner.clientHeight);
  }, [chatRef, containerStyle, scrollTo]);

  return {
    autoScroll,
    onMessageListScroll,
    scrollTo,
    scrollToLesson,
    scrollToBottom,
  };
};
