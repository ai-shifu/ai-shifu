import { useCallback, useRef } from 'react';

export const useSingleFlight = <Args extends unknown[], Result>(
  action: (...args: Args) => Promise<Result> | Result,
) => {
  const inFlightRef = useRef(false);
  const actionRef = useRef(action);
  actionRef.current = action;

  return useCallback(
    async (...args: Args): Promise<Awaited<Result> | undefined> => {
      // Guard async actions against duplicate clicks while the previous call is pending.
      if (inFlightRef.current) {
        return undefined;
      }

      inFlightRef.current = true;

      try {
        return await actionRef.current(...args);
      } finally {
        inFlightRef.current = false;
      }
    },
    [],
  );
};
