import { useCallback, useMemo, useReducer } from 'react';
import type { ListenRuntimeEvent } from './events';
import { reduceListenRuntime } from './reducer';
import {
  createInitialListenRuntimeState,
  type ListenRuntimeCommand,
  type ListenRuntimeState,
} from './state';

export interface ListenOrchestratorApi {
  state: ListenRuntimeState;
  dispatchEvent: (event: ListenRuntimeEvent) => void;
  dispatchEvents: (events: ListenRuntimeEvent[]) => void;
  consumeCommands: (count?: number) => void;
  reset: () => void;
  getNextCommand: () => ListenRuntimeCommand | null;
}

export const useListenOrchestrator = (): ListenOrchestratorApi => {
  const [state, dispatch] = useReducer(
    reduceListenRuntime,
    undefined,
    createInitialListenRuntimeState,
  );

  const dispatchEvent = useCallback((event: ListenRuntimeEvent) => {
    dispatch(event);
  }, []);

  const dispatchEvents = useCallback((events: ListenRuntimeEvent[]) => {
    events.forEach(event => {
      dispatch(event);
    });
  }, []);

  const consumeCommands = useCallback((count?: number) => {
    dispatch({
      type: 'COMMANDS_CONSUMED',
      count,
    });
  }, []);

  const reset = useCallback(() => {
    dispatch({
      type: 'RESET',
    });
  }, []);

  const getNextCommand = useCallback(
    () => state.pendingCommands[0] || null,
    [state.pendingCommands],
  );

  return useMemo(
    () => ({
      state,
      dispatchEvent,
      dispatchEvents,
      consumeCommands,
      reset,
      getNextCommand,
    }),
    [
      state,
      dispatchEvent,
      dispatchEvents,
      consumeCommands,
      reset,
      getNextCommand,
    ],
  );
};
