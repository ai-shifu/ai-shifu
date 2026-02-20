import type { ListenUnitId } from './unit-id';

export type ListenRuntimeEvent =
  | {
      type: 'REGISTER_UNIT';
      unitId: ListenUnitId;
      blockBid: string;
      position: number;
      page: number;
      hasAudio?: boolean;
    }
  | { type: 'UNIT_VISUAL_READY'; unitId: ListenUnitId }
  | { type: 'UNIT_AUDIO_READY'; unitId: ListenUnitId }
  | { type: 'UNIT_AUDIO_STARTED'; unitId: ListenUnitId }
  | { type: 'UNIT_AUDIO_ENDED'; unitId: ListenUnitId }
  | { type: 'UNIT_AUDIO_ERROR'; unitId: ListenUnitId; reason?: string }
  | { type: 'INTERACTION_OPENED'; blockBid: string; page: number }
  | { type: 'INTERACTION_RESOLVED'; blockBid: string }
  | { type: 'USER_PLAY' | 'USER_PAUSE' | 'USER_NEXT' | 'USER_PREV' | 'RESET' }
  | { type: 'COMMANDS_CONSUMED'; count?: number };
