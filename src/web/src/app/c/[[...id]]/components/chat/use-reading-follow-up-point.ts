import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type RefObject,
} from 'react';

const ANCHOR_SELECTOR = '[data-reading-follow-up-anchor]';
const MARKER_SELECTOR = '[data-reading-follow-up-marker]';
const CONTROL_SELECTOR =
  'button, a, input, textarea, select, summary, label, [role="button"], [contenteditable], [data-reading-follow-up-panel]';

type TrackerOptions = {
  root: HTMLElement;
  mobile: boolean;
  isLocked: () => boolean;
  onPoint: (anchorElementBid: string | null) => void;
  supportsScrollEnd?: boolean;
};

type Tap = {
  id: number;
  element: HTMLElement;
  x: number;
  y: number;
  time: number;
  scrollVersion: number;
  invalid: boolean;
};

/** Keep DOM geometry and native event handling outside React's render lifecycle. */
export function attachReadingFollowUpPointTracker({
  root,
  mobile,
  isLocked,
  onPoint,
  supportsScrollEnd = 'onscrollend' in root,
}: TrackerOptions) {
  const page = root.ownerDocument;
  const view = page.defaultView;
  if (!view) return Object.assign(() => {}, { selectAnchor: () => {} });
  let frame: number | null = null;
  let disposed = false;
  let scrolling = false;
  let deferredEnd = false;
  let pointer: { x: number; y: number } | null = null;
  let tap: Tap | null = null;
  let scrollVersion = 0;
  let manualVersion = -1;
  let manualElement: HTMLElement | null = null;
  let keyboardElement: HTMLElement | null = null;
  const pointers = new Set<number>();
  const ancestors: HTMLElement[] = [];
  for (let parent = root.parentElement; parent; parent = parent.parentElement) {
    ancestors.push(parent);
  }
  const canUpdate = () =>
    !disposed && !isLocked() && !page.getSelection()?.toString().trim();
  const anchors = () =>
    Array.from(root.querySelectorAll<HTMLElement>(ANCHOR_SELECTOR));
  const bid = (element: HTMLElement | null) =>
    element?.dataset.readingFollowUpAnchor || null;

  function visibleBounds() {
    const viewport = view!.visualViewport;
    let top = viewport?.offsetTop ?? 0;
    let bottom = top + (viewport?.height ?? view!.innerHeight);
    let left = viewport?.offsetLeft ?? 0;
    let right = left + (viewport?.width ?? view!.innerWidth);
    for (const element of [root, ...ancestors]) {
      const style = view!.getComputedStyle(element);
      if (
        element !== root &&
        !/(auto|scroll|hidden|clip)/.test(
          `${style.overflow} ${style.overflowY} ${style.overflowX}`,
        )
      ) {
        continue;
      }
      const rect = element.getBoundingClientRect();
      top = Math.max(top, rect.top);
      bottom = Math.min(bottom, rect.bottom);
      left = Math.max(left, rect.left);
      right = Math.min(right, rect.right);
    }
    for (const header of page.querySelectorAll<HTMLElement>(
      'header, [data-reading-follow-up-occluder]',
    )) {
      const position = view!.getComputedStyle(header).position;
      if (position !== 'fixed' && position !== 'sticky') continue;
      const rect = header.getBoundingClientRect();
      if (rect.left < right && rect.right > left && rect.top <= top) {
        top = Math.max(top, rect.bottom);
      }
    }
    return { top, bottom, left, right };
  }

  function hasVisibleMarker(element: HTMLElement) {
    const marker = element.querySelector<HTMLElement>(MARKER_SELECTOR);
    if (!marker) return false;
    const rect = marker.getBoundingClientRect();
    const bounds = visibleBounds();
    return (
      rect.height > 0 &&
      rect.width > 0 &&
      rect.top >= bounds.top &&
      rect.bottom <= bounds.bottom &&
      rect.left >= bounds.left &&
      rect.right <= bounds.right
    );
  }

  function viewportPoint() {
    const bounds = visibleBounds();
    const readingLine = bounds.top + (bounds.bottom - bounds.top) * 0.4;
    let best: HTMLElement | null = null;
    let distance = Infinity;
    for (const element of anchors()) {
      const rect = element.getBoundingClientRect();
      if (rect.bottom < bounds.top || rect.top > bounds.bottom) continue;
      if (mobile) {
        if (
          hasVisibleMarker(element) &&
          (!best ||
            element.querySelector(MARKER_SELECTOR)!.getBoundingClientRect()
              .bottom >
              best.querySelector(MARKER_SELECTOR)!.getBoundingClientRect()
                .bottom)
        ) {
          best = element;
        }
      } else {
        const nextDistance = Math.max(
          rect.top - readingLine,
          readingLine - rect.bottom,
          0,
        );
        if (nextDistance < distance) {
          best = element;
          distance = nextDistance;
        }
      }
    }
    return best;
  }

  function paragraphFor(target: EventTarget | null) {
    if (
      !(target instanceof view!.Element) ||
      target.closest(CONTROL_SELECTOR)
    ) {
      return null;
    }
    const element = target.closest<HTMLElement>(ANCHOR_SELECTOR);
    return element && root.contains(element) ? element : null;
  }

  function currentPoint() {
    if (
      keyboardElement &&
      root.contains(keyboardElement) &&
      keyboardElement.contains(page.activeElement) &&
      hasVisibleMarker(keyboardElement)
    )
      return keyboardElement;
    if (mobile) {
      if (manualVersion === scrollVersion && manualElement) {
        return root.contains(manualElement) && hasVisibleMarker(manualElement)
          ? manualElement
          : null;
      }
      return viewportPoint();
    }
    const hovered = pointer
      ? paragraphFor(page.elementFromPoint?.(pointer.x, pointer.y))
      : null;
    return hovered || viewportPoint();
  }

  function commit(element: HTMLElement | null) {
    if (canUpdate()) onPoint(bid(element));
  }

  function cancelFrame() {
    if (frame !== null) view!.cancelAnimationFrame(frame);
    frame = null;
  }

  function settle() {
    if (mobile && pointers.size) {
      deferredEnd = true;
      return;
    }
    cancelFrame();
    deferredEnd = false;
    scrolling = false;
    commit(currentPoint());
  }

  function position() {
    return [
      view!.scrollX,
      view!.scrollY,
      ...[root, ...ancestors].flatMap(element => [
        element.scrollLeft,
        element.scrollTop,
      ]),
    ].join(':');
  }

  function watchScrollFrames() {
    cancelFrame();
    let previous = position();
    let stable = 0;
    const check = () => {
      frame = null;
      if (disposed) return;
      const next = position();
      stable = next === previous && !(mobile && pointers.size) ? stable + 1 : 0;
      previous = next;
      if (stable >= 2) settle();
      else frame = view!.requestAnimationFrame(check);
    };
    frame = view!.requestAnimationFrame(check);
  }

  function relevantScroll(event: Event) {
    return (
      event.target === page ||
      event.target === view ||
      event.target === root ||
      ancestors.includes(event.target as HTMLElement)
    );
  }

  function onScroll(event: Event) {
    if (!relevantScroll(event)) return;
    scrolling = true;
    deferredEnd = false;
    scrollVersion += 1;
    manualElement = null;
    manualVersion = -1;
    if (!supportsScrollEnd) watchScrollFrames();
  }

  function onScrollEnd(event: Event) {
    if (relevantScroll(event)) settle();
  }

  function onPointerDown(event: PointerEvent) {
    if (!mobile || event.button > 0) return;
    pointers.add(event.pointerId);
    if (pointers.size > 1 || event.isPrimary === false) {
      if (tap) tap.invalid = true;
      return;
    }
    const element = canUpdate() ? paragraphFor(event.target) : null;
    if (element) keyboardElement = null;
    tap = element
      ? {
          id: event.pointerId,
          element,
          x: event.clientX,
          y: event.clientY,
          time: event.timeStamp,
          scrollVersion,
          invalid: false,
        }
      : null;
  }

  function onPointerMove(event: PointerEvent) {
    if (mobile) {
      if (
        tap?.id === event.pointerId &&
        Math.hypot(event.clientX - tap.x, event.clientY - tap.y) > 10
      ) {
        tap.invalid = true;
      }
      return;
    }
    if (event.pointerType !== 'mouse' && event.pointerType !== 'pen') return;
    pointer = { x: event.clientX, y: event.clientY };
    if (!scrolling) {
      const element = paragraphFor(event.target);
      if (element) {
        keyboardElement = null;
        commit(element);
      }
    }
  }

  function onPointerUp(event: PointerEvent) {
    if (!mobile) return;
    pointers.delete(event.pointerId);
    const gesture = tap?.id === event.pointerId ? tap : null;
    if (gesture) tap = null;
    if (
      gesture &&
      !pointers.size &&
      !gesture.invalid &&
      event.timeStamp - gesture.time < 500 &&
      Math.hypot(event.clientX - gesture.x, event.clientY - gesture.y) <= 10 &&
      gesture.scrollVersion === scrollVersion &&
      paragraphFor(event.target) === gesture.element &&
      canUpdate()
    ) {
      manualElement = gesture.element;
      manualVersion = scrollVersion;
      scrolling = false;
      deferredEnd = false;
      cancelFrame();
      commit(hasVisibleMarker(manualElement) ? manualElement : null);
    }
    if (deferredEnd && !pointers.size) {
      // Let a marker button's click lock its newly opened answer first.
      frame = view!.requestAnimationFrame(settle);
    }
  }

  function onPointerCancel(event: PointerEvent) {
    pointers.delete(event.pointerId);
    if (tap?.id === event.pointerId) tap = null;
    if (deferredEnd && !pointers.size)
      frame = view!.requestAnimationFrame(settle);
  }

  function onLayoutChange() {
    if (scrolling || (mobile && pointers.size)) return;
    cancelFrame();
    frame = view!.requestAnimationFrame(() => {
      frame = null;
      if (!scrolling) commit(currentPoint());
    });
  }

  function selectAnchor(anchor: string) {
    if (!canUpdate()) return;
    const element = anchors().find(candidate => bid(candidate) === anchor);
    if (!element) return;
    keyboardElement = element;
    if (mobile) {
      manualElement = element;
      manualVersion = scrollVersion;
    }
    commit(element);
  }

  commit(viewportPoint());
  page.addEventListener('pointerdown', onPointerDown);
  page.addEventListener('pointermove', onPointerMove);
  page.addEventListener('pointerup', onPointerUp);
  page.addEventListener('pointercancel', onPointerCancel);
  page.addEventListener('scroll', onScroll, true);
  if (supportsScrollEnd) page.addEventListener('scrollend', onScrollEnd, true);
  view.addEventListener('resize', onLayoutChange);
  view.visualViewport?.addEventListener('resize', onLayoutChange);
  view.visualViewport?.addEventListener('scroll', onLayoutChange);
  const observer = view.ResizeObserver
    ? new view.ResizeObserver(onLayoutChange)
    : null;
  observer?.observe(root);
  return Object.assign(
    () => {
      disposed = true;
      cancelFrame();
      observer?.disconnect();
      page.removeEventListener('pointerdown', onPointerDown);
      page.removeEventListener('pointermove', onPointerMove);
      page.removeEventListener('pointerup', onPointerUp);
      page.removeEventListener('pointercancel', onPointerCancel);
      page.removeEventListener('scroll', onScroll, true);
      if (supportsScrollEnd)
        page.removeEventListener('scrollend', onScrollEnd, true);
      view.removeEventListener('resize', onLayoutChange);
      view.visualViewport?.removeEventListener('resize', onLayoutChange);
      view.visualViewport?.removeEventListener('scroll', onLayoutChange);
    },
    { selectAnchor },
  );
}

export function useReadingFollowUpPoint({
  rootRef,
  enabled,
  mobile,
  locked,
  scopeKey,
  contentKey,
}: {
  rootRef: RefObject<HTMLElement | null>;
  enabled: boolean;
  mobile: boolean;
  locked: boolean;
  scopeKey: string;
  contentKey?: string;
}) {
  const [anchorElementBid, setAnchorElementBid] = useState<string | null>(null);
  const selectAnchorRef = useRef<(anchor: string) => void>(() => {});
  const lockedRef = useRef(locked);
  lockedRef.current = locked;
  useEffect(() => {
    const root = rootRef.current;
    if (!enabled || !root) {
      selectAnchorRef.current = () => {};
      setAnchorElementBid(null);
      return;
    }
    const detach = attachReadingFollowUpPointTracker({
      root,
      mobile,
      isLocked: () => lockedRef.current,
      onPoint: setAnchorElementBid,
    });
    selectAnchorRef.current = detach.selectAnchor;
    return () => {
      selectAnchorRef.current = () => {};
      detach();
    };
  }, [rootRef, enabled, mobile, scopeKey, contentKey]);
  const selectAnchor = useCallback(
    (anchor: string) => selectAnchorRef.current(anchor),
    [],
  );
  return { anchorElementBid, selectAnchor };
}
