import { useCallback } from "react"
import { smoothScroll } from 'Utils/smoothScroll';

// take scroll logic in the separate file
export const useChatComponentsScroll = ({
  chatRef,
  containerStyle,
}) => {
  const scrollTo = useCallback((height) => {
    const wrapper = chatRef.current?.querySelector(
      `.${containerStyle} .PullToRefresh`
    );

    if (!wrapper) {
      return;
    }
    smoothScroll({ el: wrapper, to: height });
  }, [chatRef, containerStyle]);

  const scrollToLesson = useCallback((lessonId) => {
    if (!chatRef.current) {
      return;
    }

    const lessonNode = chatRef.current.querySelector(
      `[data-id=lesson-${lessonId}]`
    );
    if (!lessonNode) {
      return;
    }

    scrollTo(lessonNode.offsetTop);
  }, [chatRef, scrollTo]);

  const scrollToBottom = useCallback(() => {
    const inner = chatRef.current?.querySelector(
      `.${containerStyle} .PullToRefresh-inner`
    );

    if (!inner) {
      return;
    }

    scrollTo(inner.clientHeight);
  }, [chatRef, containerStyle, scrollTo]);

  return {
    scrollTo,
    scrollToLesson,
    scrollToBottom,
  }
}
