const ua = navigator.userAgent;
const iOS = /iPad|iPhone|iPod/.test(ua);

function uaIncludes(str: string) {
  return ua.indexOf(str) !== -1;
}

function testScrollType() {
  if (iOS) {
    if (uaIncludes('Safari/') || /OS 11_[0-3]\D/.test(ua)) {
      /**
       * Do nothing for these cases:
       * - Safari
       * - iOS 11.0-11.3 (there are bugs with `scrollTop`/`scrollIntoView`)
       */
      return 0;
    }
    // Use the `scrollTop` approach
    return 1;
  }
  // All other cases use `scrollIntoView`
  return 2;
}

export default function riseInput(input: HTMLElement, target: HTMLElement) {
  const scrollType = testScrollType();
  let scrollTimer: ReturnType<typeof setTimeout>;

  if (!target) {
    target = input;
  }

  const scrollIntoView = () => {
    if (scrollType === 0) return;
    if (scrollType === 1) {
      document.body.scrollTop = document.body.scrollHeight;
    } else {
      target.scrollIntoView(false);
    }
  };

  input.addEventListener('focus', () => {
    setTimeout(scrollIntoView, 300);
    scrollTimer = setTimeout(scrollIntoView, 1000);
  });

  input.addEventListener('blur', () => {
    clearTimeout(scrollTimer);

    // On some apps the input stays pushed up after the keyboard closes, leaving blank space
    // For example: Xianyu, Damai, LeDongLi, WeChat
    if (scrollType && iOS) {
      // Prevent quick phrase taps from failing
      setTimeout(() => {
        document.body.scrollIntoView();
      });
    }
  });
}
