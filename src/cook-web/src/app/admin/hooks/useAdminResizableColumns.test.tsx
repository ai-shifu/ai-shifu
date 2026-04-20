import { act, renderHook } from '@testing-library/react';
import { useAdminResizableColumns } from './useAdminResizableColumns';

const DEFAULT_WIDTHS = {
  title: 120,
  amount: 160,
} as const;

const SINGLE_COLUMN_WIDTHS = {
  title: 120,
} as const;

const getListenerCalls = (
  spy: jest.SpyInstance,
  eventName: string,
): unknown[][] => spy.mock.calls.filter(([type]) => type === eventName);

describe('useAdminResizableColumns', () => {
  beforeEach(() => {
    jest.restoreAllMocks();
    window.localStorage.clear();
  });

  test('only attaches window listeners while a resize is active', () => {
    const addEventListenerSpy = jest.spyOn(window, 'addEventListener');
    const removeEventListenerSpy = jest.spyOn(window, 'removeEventListener');
    const setItemSpy = jest.spyOn(Storage.prototype, 'setItem');

    const { result } = renderHook(() =>
      useAdminResizableColumns({
        storageKey: 'admin-table-widths',
        defaultWidths: DEFAULT_WIDTHS,
      }),
    );

    expect(getListenerCalls(addEventListenerSpy, 'mousemove')).toHaveLength(0);
    expect(getListenerCalls(addEventListenerSpy, 'mouseup')).toHaveLength(0);

    act(() => {
      result.current.getResizeHandleProps('title').onMouseDown({
        preventDefault: jest.fn(),
        clientX: 100,
      } as any);
    });

    const moveListener = getListenerCalls(
      addEventListenerSpy,
      'mousemove',
    )[0]?.[1] as ((event: MouseEvent) => void) | undefined;
    const upListener = getListenerCalls(
      addEventListenerSpy,
      'mouseup',
    )[0]?.[1] as (() => void) | undefined;

    expect(moveListener).toBeDefined();
    expect(upListener).toBeDefined();

    act(() => {
      moveListener?.({ clientX: 145 } as MouseEvent);
    });

    expect(result.current.columnWidths.title).toBe(165);

    act(() => {
      upListener?.();
    });

    expect(setItemSpy).toHaveBeenCalledWith(
      'admin-table-widths',
      JSON.stringify({ title: 165 }),
    );
    expect(getListenerCalls(removeEventListenerSpy, 'mousemove')).toHaveLength(
      1,
    );
    expect(getListenerCalls(removeEventListenerSpy, 'mouseup')).toHaveLength(1);
  });

  test('cleans up active resize listeners on unmount', () => {
    const removeEventListenerSpy = jest.spyOn(window, 'removeEventListener');

    const { result, unmount } = renderHook(() =>
      useAdminResizableColumns({
        storageKey: 'admin-table-widths',
        defaultWidths: SINGLE_COLUMN_WIDTHS,
      }),
    );

    act(() => {
      result.current.getResizeHandleProps('title').onMouseDown({
        preventDefault: jest.fn(),
        clientX: 100,
      } as any);
    });

    unmount();

    expect(getListenerCalls(removeEventListenerSpy, 'mousemove')).toHaveLength(
      1,
    );
    expect(getListenerCalls(removeEventListenerSpy, 'mouseup')).toHaveLength(1);
  });
});
