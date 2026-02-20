import type { ListenUnitId } from './unit-id';

export type ListenUnitVisualStatus = 'pending' | 'ready' | 'displayed';
export type ListenUnitAudioStatus =
  | 'missing'
  | 'pending'
  | 'ready'
  | 'playing'
  | 'done'
  | 'error';

export type ListenRuntimeMode =
  | 'idle'
  | 'waiting_audio'
  | 'playing'
  | 'paused'
  | 'interaction_blocked'
  | 'ended'
  | 'error';

export type ListenRuntimeCommand =
  | { id: number; type: 'SHOW_PAGE'; unitId: ListenUnitId; page: number }
  | { id: number; type: 'PLAY_UNIT_AUDIO'; unitId: ListenUnitId }
  | { id: number; type: 'PAUSE_AUDIO'; unitId: ListenUnitId };

export interface ListenUnitState {
  unitId: ListenUnitId;
  blockBid: string;
  position: number;
  page: number;
  visualStatus: ListenUnitVisualStatus;
  audioStatus: ListenUnitAudioStatus;
}

export interface ListenRuntimeState {
  mode: ListenRuntimeMode;
  unitsInOrder: ListenUnitId[];
  units: Partial<Record<ListenUnitId, ListenUnitState>>;
  activeUnitId: ListenUnitId | null;
  blockedInteraction: { blockBid: string; page: number } | null;
  pendingCommands: ListenRuntimeCommand[];
  nextCommandId: number;
  lastError: string | null;
}

export const createInitialListenRuntimeState = (): ListenRuntimeState => ({
  mode: 'idle',
  unitsInOrder: [],
  units: {},
  activeUnitId: null,
  blockedInteraction: null,
  pendingCommands: [],
  nextCommandId: 1,
  lastError: null,
});
