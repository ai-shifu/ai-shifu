import {
  attachBrowserHistoryGuardBridge,
  getBrowserHistoryIndex,
  isBrowserHistoryBridgeTraversing,
  registerBrowserHistoryGuard,
  resumeBrowserHistoryTraversal,
} from './browserHistoryGuard';

describe('browserHistoryGuard', () => {
  let detachBridge: (() => void) | undefined;

  beforeEach(() => {
    window.history.replaceState({ __NA: true }, '', '/');
  });

  afterEach(() => {
    detachBridge?.();
    detachBridge = undefined;
    jest.restoreAllMocks();
    jest.useRealTimers();
  });

  test('indexes the current entry and preserves monotonic indexes across push and replace', () => {
    detachBridge = attachBrowserHistoryGuardBridge();

    expect(getBrowserHistoryIndex(window.history.state)).toBe(0);
    window.history.pushState({ page: 'one' }, '', '/one');
    expect(getBrowserHistoryIndex(window.history.state)).toBe(1);
    expect(window.history.state).toEqual(
      expect.objectContaining({ page: 'one' }),
    );
    window.history.replaceState({ page: 'one-replaced' }, '', '/one-replaced');
    expect(getBrowserHistoryIndex(window.history.state)).toBe(1);
    expect(window.history.state).toEqual(
      expect.objectContaining({ page: 'one-replaced' }),
    );
    window.history.pushState({ page: 'two' }, '', '/two');
    expect(getBrowserHistoryIndex(window.history.state)).toBe(2);
  });

  test('restores the source entry before notifying a guard, then resumes the exact target', async () => {
    detachBridge = attachBrowserHistoryGuardBridge();
    const initialState = window.history.state;
    window.history.pushState({ page: 'one' }, '', '/one');
    window.history.pushState({ page: 'two' }, '', '/two');
    const sourceState = window.history.state;
    const go = jest.spyOn(window.history, 'go').mockImplementation(() => {});
    const guard = jest.fn();
    const unregister = registerBrowserHistoryGuard(guard);
    const downstreamPopState = jest.fn();
    window.addEventListener('popstate', downstreamPopState);

    window.dispatchEvent(
      new PopStateEvent('popstate', { state: initialState }),
    );

    expect(go).toHaveBeenCalledWith(2);
    expect(guard).not.toHaveBeenCalled();
    expect(downstreamPopState).not.toHaveBeenCalled();
    expect(isBrowserHistoryBridgeTraversing()).toBe(true);

    window.dispatchEvent(new PopStateEvent('popstate', { state: sourceState }));

    expect(guard).toHaveBeenCalledWith({
      fallbackUrl: null,
      targetIndex: 0,
    });
    expect(downstreamPopState).toHaveBeenCalledTimes(1);
    expect(isBrowserHistoryBridgeTraversing()).toBe(false);

    const resumed = resumeBrowserHistoryTraversal(0);
    expect(go).toHaveBeenLastCalledWith(-2);
    window.dispatchEvent(
      new PopStateEvent('popstate', { state: initialState }),
    );
    await expect(resumed).resolves.toBeUndefined();
    expect(downstreamPopState).toHaveBeenCalledTimes(2);
    expect(isBrowserHistoryBridgeTraversing()).toBe(false);

    window.removeEventListener('popstate', downstreamPopState);
    unregister();
  });

  test('restores the source before guarding a forward traversal', () => {
    detachBridge = attachBrowserHistoryGuardBridge();
    const initialState = window.history.state;
    window.history.pushState({ page: 'one' }, '', '/one');
    window.history.pushState({ page: 'two' }, '', '/two');
    const forwardState = window.history.state;
    window.dispatchEvent(
      new PopStateEvent('popstate', { state: initialState }),
    );
    const go = jest.spyOn(window.history, 'go').mockImplementation(() => {});
    const guard = jest.fn();
    const unregister = registerBrowserHistoryGuard(guard);

    window.dispatchEvent(
      new PopStateEvent('popstate', { state: forwardState }),
    );
    expect(go).toHaveBeenCalledWith(-2);
    expect(guard).not.toHaveBeenCalled();

    window.dispatchEvent(
      new PopStateEvent('popstate', { state: initialState }),
    );
    expect(guard).toHaveBeenCalledWith({
      fallbackUrl: null,
      targetIndex: 2,
    });
    expect(isBrowserHistoryBridgeTraversing()).toBe(false);

    unregister();
  });

  test.each([
    [
      'throws',
      () => {
        throw new Error('history.go failed');
      },
    ],
    ['does not emit popstate', () => undefined],
  ])(
    'realigns the source and exposes a route fallback when restoration %s',
    (_label, goImplementation) => {
      jest.useFakeTimers();
      const replaceState = window.history.replaceState.bind(window.history);
      detachBridge = attachBrowserHistoryGuardBridge();
      const targetState = window.history.state;
      const targetIndex = getBrowserHistoryIndex(targetState);
      const targetUrl = window.location.href;
      window.history.pushState(
        { page: 'profile-onboarding' },
        '',
        '/profile-onboarding',
      );
      const sourceUrl = window.location.href;
      replaceState(targetState, '', '/');
      const go = jest
        .spyOn(window.history, 'go')
        .mockImplementation(goImplementation);
      const guard = jest.fn();
      const unregister = registerBrowserHistoryGuard(guard);

      window.dispatchEvent(
        new PopStateEvent('popstate', { state: targetState }),
      );
      expect(isBrowserHistoryBridgeTraversing()).toBe(true);

      jest.advanceTimersByTime(2000);

      expect(go).toHaveBeenCalledTimes(2);
      expect(guard).toHaveBeenCalledWith({
        fallbackUrl: targetUrl,
        targetIndex: null,
      });
      expect(window.location.href).toBe(sourceUrl);
      expect(getBrowserHistoryIndex(window.history.state)).toBe(targetIndex);
      expect(isBrowserHistoryBridgeTraversing()).toBe(false);

      unregister();
    },
  );

  test('does not overshoot when restoration reaches the source before popstate', () => {
    jest.useFakeTimers();
    const replaceState = window.history.replaceState.bind(window.history);
    detachBridge = attachBrowserHistoryGuardBridge();
    const targetState = window.history.state;
    const targetIndex = getBrowserHistoryIndex(targetState);
    window.history.pushState({ page: 'source' }, '', '/source');
    const sourceState = window.history.state;
    replaceState(targetState, '', '/');
    const go = jest.spyOn(window.history, 'go').mockImplementation(() => {
      replaceState(sourceState, '', '/source');
    });
    const guard = jest.fn();
    const unregister = registerBrowserHistoryGuard(guard);

    window.dispatchEvent(new PopStateEvent('popstate', { state: targetState }));
    jest.advanceTimersByTime(1000);

    expect(go).toHaveBeenCalledTimes(1);
    expect(guard).toHaveBeenCalledWith({
      fallbackUrl: null,
      targetIndex,
    });
    expect(getBrowserHistoryIndex(window.history.state)).toBe(
      getBrowserHistoryIndex(sourceState),
    );
    expect(isBrowserHistoryBridgeTraversing()).toBe(false);

    unregister();
  });

  test('times out an allowed history.go replay and permits a later retry', async () => {
    jest.useFakeTimers();
    detachBridge = attachBrowserHistoryGuardBridge();
    const targetState = window.history.state;
    window.history.pushState({ page: 'source' }, '', '/source');
    const go = jest.spyOn(window.history, 'go').mockImplementation(() => {});

    const firstReplay = resumeBrowserHistoryTraversal(0);
    const firstResult = expect(firstReplay).rejects.toThrow(
      'browser-history traversal did not complete',
    );
    jest.advanceTimersByTime(5000);
    await firstResult;
    expect(isBrowserHistoryBridgeTraversing()).toBe(false);

    const secondReplay = resumeBrowserHistoryTraversal(0);
    window.dispatchEvent(new PopStateEvent('popstate', { state: targetState }));
    await expect(secondReplay).resolves.toBeUndefined();
    expect(go).toHaveBeenCalledTimes(2);
    expect(isBrowserHistoryBridgeTraversing()).toBe(false);
  });

  test('completes a replay that reaches its target before popstate', async () => {
    jest.useFakeTimers();
    const replaceState = window.history.replaceState.bind(window.history);
    detachBridge = attachBrowserHistoryGuardBridge();
    const targetState = window.history.state;
    const targetIndex = getBrowserHistoryIndex(targetState);
    window.history.pushState({ page: 'source' }, '', '/source');
    const go = jest.spyOn(window.history, 'go').mockImplementation(() => {
      replaceState(targetState, '', '/');
    });

    const replay = resumeBrowserHistoryTraversal(targetIndex);
    jest.advanceTimersByTime(5000);

    await expect(replay).resolves.toBeUndefined();
    expect(go).toHaveBeenCalledTimes(1);
    expect(isBrowserHistoryBridgeTraversing()).toBe(false);
    await expect(
      resumeBrowserHistoryTraversal(targetIndex),
    ).resolves.toBeUndefined();
    expect(go).toHaveBeenCalledTimes(1);
  });

  test('keeps an accepted Navigation API bypass until its popstate arrives', async () => {
    detachBridge = attachBrowserHistoryGuardBridge();
    const targetState = window.history.state;
    window.history.pushState({ page: 'source' }, '', '/source');

    const replay = resumeBrowserHistoryTraversal(null, () => Promise.resolve());
    await Promise.resolve();

    expect(isBrowserHistoryBridgeTraversing()).toBe(true);
    window.dispatchEvent(new PopStateEvent('popstate', { state: targetState }));
    await expect(replay).resolves.toBeUndefined();
    expect(isBrowserHistoryBridgeTraversing()).toBe(false);
  });

  test.each([
    [
      'throws synchronously',
      () => {
        throw new Error('traverseTo failed');
      },
    ],
    [
      'rejects asynchronously',
      () => Promise.reject(new Error('traverseTo rejected')),
    ],
  ])('releases an allowed traversal when replay %s', async (_label, start) => {
    detachBridge = attachBrowserHistoryGuardBridge();

    await expect(resumeBrowserHistoryTraversal(null, start)).rejects.toThrow(
      'browser-history traversal failed',
    );
    expect(isBrowserHistoryBridgeTraversing()).toBe(false);
  });
});
