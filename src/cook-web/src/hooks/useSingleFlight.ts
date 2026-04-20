import { useCallback, useRef } from 'react';

export const useSingleFlight = <Args extends unknown[], Result>(
  action: (...args: Args) => Promise<Result> | Result,
) => {
  const inFlightRef = useRef(false);

  return useCallback(
    async (...args: Args) => {
      // Guard async actions against duplicate clicks while the previous call is pending.
      if (inFlightRef.current) {
        return undefined;
      }

      inFlightRef.current = true;

      try {
        return await action(...args);
      } finally {
        inFlightRef.current = false;
      }
    },
    [action],
  );
};
