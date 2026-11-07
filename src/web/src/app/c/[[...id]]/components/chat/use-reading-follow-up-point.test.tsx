import { act, renderHook } from '@testing-library/react';
import {
  attachReadingFollowUpPointTracker,
  useReadingFollowUpPoint,
} from './use-reading-follow-up-point';

const rect = (top: number, bottom: number, left = 20, right = 380) =>
  ({
    top,
    bottom,
    left,
    right,
    width: right - left,
    height: bottom - top,
    x: left,
    y: top,
    toJSON: () => ({}),
  }) as DOMRect;

function bounds(element: Element, top: number, bottom: number) {
  jest
    .spyOn(element, 'getBoundingClientRect')
    .mockReturnValue(rect(top, bottom));
}

function pointer(
  target: Element,
  type: string,
  options: Partial<PointerEvent> = {},
) {
  const event = new Event(type, { bubbles: true });
  Object.defineProperties(
    event,
    Object.fromEntries(
      Object.entries({
        pointerId: 1,
        pointerType: 'touch',
        isPrimary: true,
        button: 0,
        clientX: 100,
        clientY: 200,
        timeStamp: 100,
        ...options,
      }).map(([key, value]) => [key, { value }]),
    ),
  );
  target.dispatchEvent(event);
}

function fixture({ mobile = false, native = true } = {}) {
  document.body.innerHTML =
    '<main style="overflow:auto"><div id="root"></div></main>';
  const outer = document.querySelector('main')!;
  const root = document.getElementById('root')!;
  bounds(outer, 100, 800);
  bounds(root, 0, 1000);
  Object.defineProperty(window, 'innerWidth', {
    value: 400,
    configurable: true,
  });
  Object.defineProperty(window, 'innerHeight', {
    value: 900,
    configurable: true,
  });
  const elements = ['a', 'b', 'c'].map((id, index) => {
    const element = document.createElement('div');
    element.dataset.readingFollowUpAnchor = id;
    element.innerHTML = `<p>Course content ${id}</p><div data-reading-follow-up-marker></div>`;
    root.appendChild(element);
    const top = [120, 350, 700][index];
    const bottom = [250, 500, 850][index];
    bounds(element, top, bottom);
    bounds(
      element.querySelector('[data-reading-follow-up-marker]')!,
      bottom,
      bottom + 44,
    );
    return element;
  });
  let locked = false;
  const points: Array<string | null> = [];
  const frames = new Map<number, FrameRequestCallback>();
  let frameId = 0;
  jest.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => {
    frames.set(++frameId, callback);
    return frameId;
  });
  jest.spyOn(window, 'cancelAnimationFrame').mockImplementation(id => {
    frames.delete(id);
  });
  Object.defineProperty(document, 'elementFromPoint', {
    value: jest.fn(() => elements[0].querySelector('p')),
    configurable: true,
  });
  const dispose = attachReadingFollowUpPointTracker({
    root,
    mobile,
    isLocked: () => locked,
    onPoint: point => points.push(point),
    supportsScrollEnd: native,
  });
  return {
    root,
    outer,
    elements,
    points,
    frames,
    dispose,
    lock: (value: boolean) => {
      locked = value;
    },
    scroll: () => outer.dispatchEvent(new Event('scroll')),
    end: () => outer.dispatchEvent(new Event('scrollend')),
    frame: () => {
      const callbacks = [...frames.values()];
      frames.clear();
      callbacks.forEach(callback => callback(0));
    },
    tap: (index: number, duration = 80) => {
      const target = elements[index].querySelector('p')!;
      pointer(target, 'pointerdown');
      pointer(target, 'pointerup', { timeStamp: 100 + duration });
    },
  };
}

afterEach(() => {
  jest.restoreAllMocks();
  document.body.innerHTML = '';
  window.getSelection()?.removeAllRanges();
});

test('desktop hover is immediate, leaving content preserves the point, and scrollend rechecks the pointer', () => {
  const f = fixture();
  expect(f.points).toEqual(['b']);
  pointer(f.elements[0].querySelector('p')!, 'pointermove', {
    pointerType: 'mouse',
  });
  expect(f.points.at(-1)).toBe('a');
  pointer(document.body, 'pointermove', { pointerType: 'mouse' });
  expect(f.points.at(-1)).toBe('a');
  f.scroll();
  pointer(f.elements[2].querySelector('p')!, 'pointermove', {
    pointerType: 'pen',
  });
  expect(f.points.at(-1)).toBe('a');
  (document.elementFromPoint as jest.Mock).mockReturnValue(
    f.elements[1].querySelector('p'),
  );
  f.end();
  expect(f.points.at(-1)).toBe('b');
  expect(f.frames.size).toBe(0);
  f.dispose();
});

test('mobile chooses the lowest complete marker clipped by the actual nested scroll container', () => {
  const f = fixture({ mobile: true });
  expect(f.points).toEqual(['b']);
  bounds(f.outer, 100, 900);
  f.scroll();
  expect(f.points.at(-1)).toBe('b');
  f.end();
  expect(f.points.at(-1)).toBe('c');
  f.dispose();
});

test('mobile hides a clipped or offscreen long-paragraph ending instead of pointing to its unseen end', () => {
  const f = fixture({ mobile: true });
  bounds(
    f.elements[0].querySelector('[data-reading-follow-up-marker]')!,
    90,
    134,
  );
  bounds(
    f.elements[1].querySelector('[data-reading-follow-up-marker]')!,
    790,
    834,
  );
  f.scroll();
  f.end();
  expect(f.points.at(-1)).toBeNull();
  f.dispose();
});

test('fixed headers and the visual viewport constrain the mobile candidate', () => {
  const f = fixture({ mobile: true });
  const header = document.createElement('header');
  header.style.position = 'fixed';
  document.body.appendChild(header);
  bounds(header, 0, 300);
  bounds(
    f.elements[1].querySelector('[data-reading-follow-up-marker]')!,
    280,
    324,
  );
  f.scroll();
  f.end();
  expect(f.points.at(-1)).toBeNull();
  header.remove();
  Object.defineProperty(window, 'visualViewport', {
    configurable: true,
    value: {
      offsetTop: 0,
      offsetLeft: 0,
      width: 400,
      height: 300,
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
    },
  });
  f.scroll();
  f.end();
  expect(f.points.at(-1)).toBe('a');
  Object.defineProperty(window, 'visualViewport', {
    value: undefined,
    configurable: true,
  });
  f.dispose();
});

test('mobile short taps retarget immediately and survive a late scrollend until the next scroll', () => {
  const f = fixture({ mobile: true });
  f.scroll();
  f.end();
  f.tap(0);
  expect(f.points.at(-1)).toBe('a');
  f.end();
  expect(f.points.at(-1)).toBe('a');
  f.scroll();
  f.end();
  expect(f.points.at(-1)).toBe('b');
  f.tap(2);
  expect(f.points.at(-1)).toBeNull();
  f.dispose();
});

test('mobile ignores hover, swipes, long presses, cancellation and multi-pointer taps', () => {
  const f = fixture({ mobile: true });
  const target = f.elements[0].querySelector('p')!;
  pointer(target, 'pointermove', { pointerType: 'mouse' });
  expect(f.points).toEqual(['b']);
  pointer(target, 'pointerdown');
  pointer(target, 'pointermove', { clientY: 220 });
  pointer(target, 'pointerup', { clientY: 220, timeStamp: 180 });
  f.tap(0, 500);
  pointer(target, 'pointerdown');
  pointer(target, 'pointercancel');
  pointer(target, 'pointerup');
  pointer(target, 'pointerdown');
  pointer(target, 'pointerdown', { pointerId: 2, isPrimary: false });
  pointer(target, 'pointerup', { pointerId: 2 });
  pointer(target, 'pointerup');
  expect(f.points).toEqual(['b']);
  f.dispose();
});

test('interactive descendants, active selection and locking cannot retarget', () => {
  const f = fixture({ mobile: true });
  const button = document.createElement('button');
  f.elements[0].appendChild(button);
  pointer(button, 'pointerdown');
  pointer(button, 'pointerup', { timeStamp: 180 });
  const range = document.createRange();
  range.selectNodeContents(f.elements[0].querySelector('p')!);
  window.getSelection()?.addRange(range);
  f.tap(0);
  f.scroll();
  f.end();
  window.getSelection()?.removeAllRanges();
  f.lock(true);
  f.tap(0);
  f.scroll();
  f.end();
  expect(f.points).toEqual(['b']);
  f.lock(false);
  f.frame();
  expect(f.points).toEqual(['b']);
  f.dispose();
});

test('fallback waits for nested scroll stability and a held pointer without a timer', () => {
  const f = fixture({ mobile: true, native: false });
  f.tap(0);
  const target = f.elements[0].querySelector('p')!;
  pointer(target, 'pointerdown');
  f.scroll();
  f.frame();
  f.frame();
  expect(f.points.at(-1)).toBe('a');
  f.outer.scrollTop = 10;
  f.frame();
  pointer(target, 'pointerup', { clientY: 240, timeStamp: 180 });
  f.frame();
  expect(f.points.at(-1)).toBe('a');
  f.frame();
  expect(f.points.at(-1)).toBe('b');
  f.dispose();
});

test('unrelated descendant scrolling does not replace a manual reading location', () => {
  const f = fixture({ mobile: true });
  f.tap(0);
  f.elements[1].dispatchEvent(new Event('scroll', { bubbles: true }));
  f.elements[1].dispatchEvent(new Event('scrollend', { bubbles: true }));
  expect(f.points.at(-1)).toBe('a');
  f.dispose();
});

test('cleanup removes handlers and queued fallback work', () => {
  const f = fixture({ mobile: true, native: false });
  f.scroll();
  expect(f.frames.size).toBe(1);
  const count = f.points.length;
  f.dispose();
  f.frame();
  f.tap(0);
  f.scroll();
  expect(f.points).toHaveLength(count);
  expect(f.frames.size).toBe(0);
});

test('the hook disables outside read mode and does not reset the point on unlock', () => {
  const f = fixture({ mobile: true });
  f.dispose();
  const rootRef = { current: f.root };
  const { result, rerender, unmount } = renderHook(
    ({ enabled, locked }) =>
      useReadingFollowUpPoint({
        rootRef,
        enabled,
        locked,
        mobile: true,
        scopeKey: 'lesson',
      }),
    { initialProps: { enabled: true, locked: false } },
  );
  expect(result.current.anchorElementBid).toBe('b');
  act(() => f.tap(0));
  expect(result.current.anchorElementBid).toBe('a');
  rerender({ enabled: true, locked: true });
  rerender({ enabled: true, locked: false });
  expect(result.current.anchorElementBid).toBe('a');
  rerender({ enabled: false, locked: false });
  expect(result.current.anchorElementBid).toBeNull();
  unmount();
});

test('semantic button focus can select a point and retains it during native focus scrolling', () => {
  const f = fixture({ mobile: true });
  const marker = f.elements[0].querySelector(
    '[data-reading-follow-up-marker]',
  )!;
  const button = document.createElement('button');
  marker.appendChild(button);
  button.focus();
  f.dispose.selectAnchor('a');
  expect(f.points.at(-1)).toBe('a');
  f.scroll();
  f.end();
  expect(f.points.at(-1)).toBe('a');
  f.lock(true);
  f.dispose.selectAnchor('b');
  expect(f.points.at(-1)).toBe('a');
  f.lock(false);
  f.dispose.selectAnchor('missing');
  expect(f.points.at(-1)).toBe('a');
  f.dispose();
});
