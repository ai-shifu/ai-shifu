const testCache = {
  passiveListener: () => {
    let supportsPassive = false;
    try {
      const opts = Object.defineProperty({}, 'passive', {
        get() {
          supportsPassive = true;
        },
      });
      // @ts-expect-error EXPECT
      window.addEventListener('test', null, opts);
    } catch (e) {
      console.log(e)
      // No support
    }
    return supportsPassive;
  },
  smoothScroll: () => 'scrollBehavior' in document.documentElement.style,
  touch: () => 'ontouchstart' in window,
};

export function addTest(name: string, test: () => unknown) {
  testCache[name] = test();
}

export default function canUse(name: string) {
  return testCache[name]();
}
