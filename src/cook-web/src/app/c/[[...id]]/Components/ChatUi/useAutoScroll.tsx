import { useEffect, useRef, useCallback } from 'react';

function useAutoScroll(containerRef: React.RefObject<HTMLElement>, opts?: {
  bottomSelector?: string,
  threshold?: number // px from bottom considered "at bottom"
}) {
  const bottomSelector = opts?.bottomSelector ?? '#chat-box-bottom';
  const threshold = opts?.threshold ?? 120;
  const autoScrollRef = useRef(true);
  const moRef = useRef<MutationObserver | null>(null);
  const roRef = useRef<ResizeObserver | null>(null);

  // track user scroll intent
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onScroll = () => {
      const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      // within threshold => still at bottom
      autoScrollRef.current = distanceToBottom <= threshold;
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    // init
    onScroll();
    return () => el.removeEventListener('scroll', onScroll);
  }, [containerRef, threshold]);

  const scrollToBottom = useCallback((behavior: 'auto' | 'smooth' = 'auto') => {
    const el = containerRef.current;
    if (!el) return;
    const bottomEl = el.querySelector(bottomSelector) as HTMLElement | null || el.lastElementChild as HTMLElement | null;
    const doScroll = () => {
      if (bottomEl && bottomEl.scrollIntoView) {
        bottomEl.scrollIntoView({ behavior, block: 'end' });
      } else {
        el.scrollTop = el.scrollHeight;
      }
    };
    doScroll();
    requestAnimationFrame(doScroll);
    setTimeout(doScroll, 40);
  }, [containerRef, bottomSelector]);

  // auto scroll when DOM changes (but only if user hasn't scrolled away)
  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof MutationObserver === 'undefined') return;

    moRef.current = new MutationObserver(() => {
      if (autoScrollRef.current) {
        // schedule after layout
        requestAnimationFrame(() => scrollToBottom('auto'));
      }
    });

    moRef.current.observe(el, { childList: true, subtree: true, characterData: true });

    // optional: also observe last child size changes
    if (typeof ResizeObserver !== 'undefined') {
      roRef.current = new ResizeObserver(() => {
        if (autoScrollRef.current) requestAnimationFrame(() => scrollToBottom('auto'));
      });
      if (el.lastElementChild) roRef.current.observe(el.lastElementChild);
    }

    return () => {
      moRef.current?.disconnect();
      roRef.current?.disconnect();
      moRef.current = null;
      roRef.current = null;
    };
  }, [containerRef, scrollToBottom]);

  return { scrollToBottom, enableAutoScroll: () => { autoScrollRef.current = true }, disableAutoScroll: () => { autoScrollRef.current = false } };
}


export default useAutoScroll;