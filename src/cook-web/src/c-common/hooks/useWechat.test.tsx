import { renderHook } from '@testing-library/react';

const mockedInWechat = jest.fn();

jest.mock('@/c-constants/uiConstants', () => ({
  inWechat: () => mockedInWechat(),
}));

describe('useWechat', () => {
  beforeEach(() => {
    jest.resetModules();
    mockedInWechat.mockReset();
    delete (globalThis as typeof globalThis & { WeixinJSBridge?: unknown })
      .WeixinJSBridge;
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('reuses the same bridge-ready promise across rerenders', async () => {
    mockedInWechat.mockReturnValue(true);

    const addEventListenerSpy = jest.spyOn(document, 'addEventListener');
    const removeEventListenerSpy = jest.spyOn(document, 'removeEventListener');
    const { useWechat } = await import('./useWechat');
    const { result, rerender } = renderHook(() => useWechat());
    const firstCallback = jest.fn();
    const secondCallback = jest.fn();

    const firstRun = result.current.runInJsBridge(firstCallback);
    rerender();
    const secondRun = result.current.runInJsBridge(secondCallback);

    expect(
      addEventListenerSpy.mock.calls.filter(
        ([eventName]) => eventName === 'WeixinJSBridgeReady',
      ),
    ).toHaveLength(1);

    document.dispatchEvent(new Event('WeixinJSBridgeReady'));

    await firstRun;
    await secondRun;

    expect(firstCallback).toHaveBeenCalledTimes(1);
    expect(secondCallback).toHaveBeenCalledTimes(1);
    expect(removeEventListenerSpy).toHaveBeenCalledWith(
      'WeixinJSBridgeReady',
      expect.any(Function),
      false,
    );
  });
});
