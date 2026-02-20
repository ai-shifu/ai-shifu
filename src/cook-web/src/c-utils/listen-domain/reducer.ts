import type { ListenRuntimeEvent } from './events';
import type {
  ListenRuntimeCommand,
  ListenRuntimeMode,
  ListenRuntimeState,
  ListenUnitState,
} from './state';
import { createInitialListenRuntimeState } from './state';
import type { ListenUnitId } from './unit-id';

const getUnit = (
  state: ListenRuntimeState,
  unitId: ListenUnitId | null,
): ListenUnitState | null => {
  if (!unitId) {
    return null;
  }
  return state.units[unitId] || null;
};

const updateUnit = (
  state: ListenRuntimeState,
  unitId: ListenUnitId,
  updater: (unit: ListenUnitState) => ListenUnitState,
): ListenRuntimeState => {
  const unit = state.units[unitId];
  if (!unit) {
    return state;
  }
  return {
    ...state,
    units: {
      ...state.units,
      [unitId]: updater(unit),
    },
  };
};

const pushCommand = (
  state: ListenRuntimeState,
  command: Omit<ListenRuntimeCommand, 'id'>,
): ListenRuntimeState => ({
  ...state,
  pendingCommands: [
    ...state.pendingCommands,
    { ...command, id: state.nextCommandId } as ListenRuntimeCommand,
  ],
  nextCommandId: state.nextCommandId + 1,
});

const resolveNextUnitId = (
  state: ListenRuntimeState,
  currentUnitId: ListenUnitId | null,
): ListenUnitId | null => {
  if (!state.unitsInOrder.length) {
    return null;
  }
  if (!currentUnitId) {
    return state.unitsInOrder[0];
  }
  const currentIndex = state.unitsInOrder.indexOf(currentUnitId);
  if (currentIndex < 0) {
    return state.unitsInOrder[0];
  }
  return state.unitsInOrder[currentIndex + 1] || null;
};

const resolvePrevUnitId = (
  state: ListenRuntimeState,
  currentUnitId: ListenUnitId | null,
): ListenUnitId | null => {
  if (!state.unitsInOrder.length) {
    return null;
  }
  if (!currentUnitId) {
    return state.unitsInOrder[0];
  }
  const currentIndex = state.unitsInOrder.indexOf(currentUnitId);
  if (currentIndex <= 0) {
    return null;
  }
  return state.unitsInOrder[currentIndex - 1];
};

const withActiveUnit = (
  state: ListenRuntimeState,
  unitId: ListenUnitId | null,
): ListenRuntimeState => {
  if (!unitId) {
    return state;
  }
  let nextState: ListenRuntimeState = {
    ...state,
    activeUnitId: unitId,
  };
  const unit = getUnit(nextState, unitId);
  if (!unit) {
    return nextState;
  }
  nextState = pushCommand(nextState, {
    type: 'SHOW_PAGE',
    unitId,
    page: unit.page,
  });
  nextState = updateUnit(nextState, unitId, current => ({
    ...current,
    visualStatus: 'displayed',
  }));
  return nextState;
};

const withPlaybackForActiveUnit = (
  state: ListenRuntimeState,
  fallbackMode: ListenRuntimeMode = 'waiting_audio',
): ListenRuntimeState => {
  const activeUnit = getUnit(state, state.activeUnitId);
  if (!activeUnit) {
    return {
      ...state,
      mode: 'idle',
    };
  }

  if (state.blockedInteraction) {
    return {
      ...state,
      mode: 'interaction_blocked',
    };
  }

  if (activeUnit.audioStatus === 'ready') {
    return pushCommand(
      {
        ...state,
        mode: 'playing',
      },
      {
        type: 'PLAY_UNIT_AUDIO',
        unitId: activeUnit.unitId,
      },
    );
  }

  if (activeUnit.audioStatus === 'playing') {
    return {
      ...state,
      mode: 'playing',
    };
  }

  if (activeUnit.audioStatus === 'done') {
    return {
      ...state,
      mode: 'ended',
    };
  }

  return {
    ...state,
    mode: fallbackMode,
  };
};

const moveToAdjacentUnit = (
  state: ListenRuntimeState,
  direction: 1 | -1,
  autoplay: boolean,
): ListenRuntimeState => {
  const targetUnitId =
    direction === 1
      ? resolveNextUnitId(state, state.activeUnitId)
      : resolvePrevUnitId(state, state.activeUnitId);

  if (!targetUnitId) {
    return state;
  }

  let nextState = withActiveUnit(state, targetUnitId);
  if (!autoplay) {
    return {
      ...nextState,
      mode: state.mode === 'paused' ? 'paused' : 'idle',
    };
  }
  nextState = withPlaybackForActiveUnit(nextState);
  return nextState;
};

const registerUnit = (
  state: ListenRuntimeState,
  event: Extract<ListenRuntimeEvent, { type: 'REGISTER_UNIT' }>,
): ListenRuntimeState => {
  const existing = state.units[event.unitId];
  if (existing) {
    return {
      ...state,
      units: {
        ...state.units,
        [event.unitId]: {
          ...existing,
          page: event.page,
          audioStatus: event.hasAudio ? 'ready' : existing.audioStatus,
        },
      },
      mode: state.mode === 'ended' ? 'idle' : state.mode,
    };
  }

  const unit: ListenUnitState = {
    unitId: event.unitId,
    blockBid: event.blockBid,
    position: event.position,
    page: event.page,
    visualStatus: 'pending',
    audioStatus: event.hasAudio ? 'ready' : 'pending',
  };

  return {
    ...state,
    unitsInOrder: [...state.unitsInOrder, event.unitId],
    units: {
      ...state.units,
      [event.unitId]: unit,
    },
    mode: state.mode === 'ended' ? 'idle' : state.mode,
  };
};

const consumeCommands = (
  state: ListenRuntimeState,
  count?: number,
): ListenRuntimeState => {
  if (!state.pendingCommands.length) {
    return state;
  }
  if (count === undefined) {
    return {
      ...state,
      pendingCommands: [],
    };
  }
  const safeCount = Math.max(0, Math.floor(count));
  if (safeCount === 0) {
    return state;
  }
  return {
    ...state,
    pendingCommands: state.pendingCommands.slice(safeCount),
  };
};

export const reduceListenRuntime = (
  state: ListenRuntimeState,
  event: ListenRuntimeEvent,
): ListenRuntimeState => {
  switch (event.type) {
    case 'RESET':
      return createInitialListenRuntimeState();
    case 'REGISTER_UNIT':
      return registerUnit(state, event);
    case 'COMMANDS_CONSUMED':
      return consumeCommands(state, event.count);
    case 'UNIT_VISUAL_READY':
      return updateUnit(state, event.unitId, unit => ({
        ...unit,
        visualStatus: 'ready',
      }));
    case 'UNIT_AUDIO_READY': {
      let nextState = updateUnit(state, event.unitId, unit => ({
        ...unit,
        audioStatus: unit.audioStatus === 'done' ? unit.audioStatus : 'ready',
      }));
      if (nextState.activeUnitId === event.unitId) {
        if (
          nextState.mode === 'waiting_audio' ||
          nextState.mode === 'playing'
        ) {
          nextState = withPlaybackForActiveUnit(nextState);
        }
      }
      return nextState;
    }
    case 'UNIT_AUDIO_STARTED':
      return {
        ...updateUnit(state, event.unitId, unit => ({
          ...unit,
          audioStatus: 'playing',
        })),
        mode: state.activeUnitId === event.unitId ? 'playing' : state.mode,
      };
    case 'UNIT_AUDIO_ERROR':
      return {
        ...updateUnit(state, event.unitId, unit => ({
          ...unit,
          audioStatus: 'error',
        })),
        mode: state.activeUnitId === event.unitId ? 'error' : state.mode,
        lastError: event.reason || 'audio_error',
      };
    case 'UNIT_AUDIO_ENDED': {
      let nextState = updateUnit(state, event.unitId, unit => ({
        ...unit,
        audioStatus: 'done',
      }));
      if (nextState.activeUnitId !== event.unitId) {
        return nextState;
      }

      const nextUnitId = resolveNextUnitId(nextState, event.unitId);
      if (!nextUnitId) {
        return {
          ...nextState,
          mode: 'ended',
        };
      }

      nextState = withActiveUnit(nextState, nextUnitId);
      nextState = withPlaybackForActiveUnit(nextState);
      return nextState;
    }
    case 'USER_PLAY': {
      const targetUnitId = state.activeUnitId || resolveNextUnitId(state, null);
      if (!targetUnitId) {
        return {
          ...state,
          mode: 'idle',
        };
      }
      let nextState = withActiveUnit(state, targetUnitId);
      nextState = withPlaybackForActiveUnit(nextState);
      return nextState;
    }
    case 'USER_PAUSE': {
      const activeUnit = getUnit(state, state.activeUnitId);
      if (!activeUnit) {
        return {
          ...state,
          mode: 'paused',
        };
      }
      let nextState: ListenRuntimeState = {
        ...state,
        mode: 'paused',
      };
      if (activeUnit.audioStatus === 'playing' || state.mode === 'playing') {
        nextState = pushCommand(nextState, {
          type: 'PAUSE_AUDIO',
          unitId: activeUnit.unitId,
        });
      }
      return nextState;
    }
    case 'USER_NEXT':
      return moveToAdjacentUnit(state, 1, state.mode === 'playing');
    case 'USER_PREV':
      return moveToAdjacentUnit(state, -1, state.mode === 'playing');
    case 'INTERACTION_OPENED': {
      let nextState: ListenRuntimeState = {
        ...state,
        blockedInteraction: {
          blockBid: event.blockBid,
          page: event.page,
        },
        mode: 'interaction_blocked',
      };
      const activeUnit = getUnit(nextState, nextState.activeUnitId);
      if (
        activeUnit &&
        (activeUnit.audioStatus === 'playing' || state.mode === 'playing')
      ) {
        nextState = pushCommand(nextState, {
          type: 'PAUSE_AUDIO',
          unitId: activeUnit.unitId,
        });
      }
      return nextState;
    }
    case 'INTERACTION_RESOLVED': {
      if (
        !state.blockedInteraction ||
        state.blockedInteraction.blockBid !== event.blockBid
      ) {
        return state;
      }
      let nextState: ListenRuntimeState = {
        ...state,
        blockedInteraction: null,
      };
      nextState = withPlaybackForActiveUnit(nextState, 'idle');
      return nextState;
    }
    default:
      return state;
  }
};
