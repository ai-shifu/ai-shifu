'use client';

import type { MouseEvent as ReactMouseEvent } from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

type ColumnWidthState<Key extends string> = Record<Key, number>;

type ColumnResizeState<Key extends string> = {
  key: Key;
  startX: number;
  startWidth: number;
};

type UseAdminResizableColumnsOptions<Key extends string> = {
  storageKey: string;
  defaultWidths: ColumnWidthState<Key>;
  minWidth?: number;
  maxWidth?: number;
};

const hasOwn = <Key extends string>(
  value: Partial<Record<Key, number>>,
  key: Key,
): boolean => Object.prototype.hasOwnProperty.call(value, key);

export function useAdminResizableColumns<Key extends string>({
  storageKey,
  defaultWidths,
  minWidth = 80,
  maxWidth = 360,
}: UseAdminResizableColumnsOptions<Key>) {
  const columnKeys = useMemo(
    () => Object.keys(defaultWidths) as Key[],
    [defaultWidths],
  );

  const clampWidth = useCallback(
    (value: number) => Math.min(maxWidth, Math.max(minWidth, value)),
    [maxWidth, minWidth],
  );

  const createColumnWidthState = useCallback(
    (overrides?: Partial<ColumnWidthState<Key>>) => {
      const widths = {} as ColumnWidthState<Key>;

      columnKeys.forEach(key => {
        const nextValue = overrides?.[key];
        const fallback = defaultWidths[key];
        widths[key] =
          typeof nextValue === 'number' && Number.isFinite(nextValue)
            ? clampWidth(nextValue)
            : clampWidth(fallback);
      });

      return widths;
    },
    [clampWidth, columnKeys, defaultWidths],
  );

  const loadStoredManualWidths = useCallback((): Partial<
    ColumnWidthState<Key>
  > => {
    if (typeof window === 'undefined') {
      return {};
    }

    try {
      const serialized = window.localStorage.getItem(storageKey);
      if (!serialized) {
        return {};
      }

      const parsed = JSON.parse(serialized) as Partial<ColumnWidthState<Key>>;
      const overrides: Partial<ColumnWidthState<Key>> = {};

      columnKeys.forEach(key => {
        const nextValue = parsed?.[key];
        if (typeof nextValue === 'number' && Number.isFinite(nextValue)) {
          overrides[key] = clampWidth(nextValue);
        }
      });

      return overrides;
    } catch {
      return {};
    }
  }, [clampWidth, columnKeys, storageKey]);

  const [hasLoadedStoredWidths, setHasLoadedStoredWidths] = useState(false);
  const columnResizeRef = useRef<ColumnResizeState<Key> | null>(null);
  const mouseMoveListenerRef = useRef<((event: MouseEvent) => void) | null>(
    null,
  );
  const mouseUpListenerRef = useRef<(() => void) | null>(null);
  const manualResizeRef = useRef<Record<Key, boolean>>(
    columnKeys.reduce(
      (acc, key) => ({
        ...acc,
        [key]: false,
      }),
      {} as Record<Key, boolean>,
    ),
  );

  const [columnWidths, setColumnWidthsState] = useState<ColumnWidthState<Key>>(
    () => createColumnWidthState(),
  );
  const columnWidthsRef = useRef(columnWidths);

  const setColumnWidths = useCallback(
    (
      value:
        | ColumnWidthState<Key>
        | ((prev: ColumnWidthState<Key>) => ColumnWidthState<Key>),
    ) => {
      setColumnWidthsState(prev => {
        const resolved = typeof value === 'function' ? value(prev) : value;
        const next = createColumnWidthState(resolved);
        const changed = columnKeys.some(
          key => Math.abs(next[key] - prev[key]) > 0.5,
        );
        if (!changed) {
          return prev;
        }
        columnWidthsRef.current = next;
        return next;
      });
    },
    [columnKeys, createColumnWidthState],
  );

  useEffect(() => {
    columnWidthsRef.current = columnWidths;
  }, [columnWidths]);

  useEffect(() => {
    const storedManualWidths = loadStoredManualWidths();
    manualResizeRef.current = columnKeys.reduce(
      (acc, key) => ({
        ...acc,
        [key]: hasOwn(storedManualWidths, key),
      }),
      {} as Record<Key, boolean>,
    );
    const nextColumnWidths = createColumnWidthState(storedManualWidths);
    columnWidthsRef.current = nextColumnWidths;
    setColumnWidthsState(nextColumnWidths);
    setHasLoadedStoredWidths(true);
  }, [columnKeys, createColumnWidthState, loadStoredManualWidths]);

  const persistManualWidths = useCallback(() => {
    if (typeof window === 'undefined' || !hasLoadedStoredWidths) {
      return;
    }

    try {
      const manualOverrides = columnKeys.reduce<Partial<ColumnWidthState<Key>>>(
        (acc, key) => {
          if (manualResizeRef.current[key]) {
            acc[key] = columnWidthsRef.current[key];
          }
          return acc;
        },
        {},
      );

      if (Object.keys(manualOverrides).length === 0) {
        window.localStorage.removeItem(storageKey);
        return;
      }

      window.localStorage.setItem(storageKey, JSON.stringify(manualOverrides));
    } catch {
      // Ignore storage errors.
    }
  }, [columnKeys, hasLoadedStoredWidths, storageKey]);

  const removeWindowListeners = useCallback(() => {
    if (typeof window === 'undefined') {
      return;
    }

    if (mouseMoveListenerRef.current) {
      window.removeEventListener('mousemove', mouseMoveListenerRef.current);
      mouseMoveListenerRef.current = null;
    }

    if (mouseUpListenerRef.current) {
      window.removeEventListener('mouseup', mouseUpListenerRef.current);
      mouseUpListenerRef.current = null;
    }
  }, []);

  const startColumnResize = useCallback(
    (key: Key, clientX: number) => {
      removeWindowListeners();
      columnResizeRef.current = {
        key,
        startX: clientX,
        startWidth: columnWidthsRef.current[key],
      };
      manualResizeRef.current[key] = true;

      if (typeof window === 'undefined') {
        return;
      }

      const handleMouseMove = (event: MouseEvent) => {
        const info = columnResizeRef.current;
        if (!info) {
          return;
        }

        const nextWidth = clampWidth(
          info.startWidth + event.clientX - info.startX,
        );
        setColumnWidthsState(prev => {
          if (Math.abs(prev[info.key] - nextWidth) < 0.5) {
            return prev;
          }
          const next = { ...prev, [info.key]: nextWidth };
          columnWidthsRef.current = next;
          return next;
        });
      };

      const handleMouseUp = () => {
        if (columnResizeRef.current) {
          persistManualWidths();
        }
        columnResizeRef.current = null;
        removeWindowListeners();
      };

      mouseMoveListenerRef.current = handleMouseMove;
      mouseUpListenerRef.current = handleMouseUp;

      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    },
    [clampWidth, persistManualWidths, removeWindowListeners],
  );

  useEffect(() => {
    return () => {
      columnResizeRef.current = null;
      removeWindowListeners();
    };
  }, [removeWindowListeners]);

  const getColumnStyle = useCallback(
    (key: Key) => {
      const width = columnWidths[key];
      return {
        width,
        minWidth: width,
        maxWidth: width,
      };
    },
    [columnWidths],
  );

  const getResizeHandleProps = useCallback(
    (key: Key) => ({
      onMouseDown: (event: ReactMouseEvent<HTMLElement>) => {
        event.preventDefault();
        startColumnResize(key, event.clientX);
      },
      'aria-hidden': 'true' as const,
    }),
    [startColumnResize],
  );

  const isManualColumn = useCallback(
    (key: Key) => manualResizeRef.current[key],
    [],
  );

  return {
    columnWidths,
    setColumnWidths,
    getColumnStyle,
    getResizeHandleProps,
    isManualColumn,
    clampWidth,
  };
}
