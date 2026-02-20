import {
  buildListenUnitId,
  createInitialListenRuntimeState,
  reduceListenRuntime,
  type ListenRuntimeCommand,
  type ListenRuntimeEvent,
  type ListenRuntimeState,
} from '@/c-utils/listen-domain';

const runEvents = (
  initial: ListenRuntimeState,
  events: ListenRuntimeEvent[],
): ListenRuntimeState =>
  events.reduce((state, event) => reduceListenRuntime(state, event), initial);

const consumeAllCommands = (state: ListenRuntimeState): ListenRuntimeState =>
  reduceListenRuntime(state, {
    type: 'COMMANDS_CONSUMED',
  });

const commandTypes = (
  state: ListenRuntimeState,
): ListenRuntimeCommand['type'][] =>
  state.pendingCommands.map(command => command.type);

describe('listen-domain reducer', () => {
  it('starts from the first unit and waits for audio when audio is not ready', () => {
    const unitId = buildListenUnitId('block-1', 0);
    const state = runEvents(createInitialListenRuntimeState(), [
      {
        type: 'REGISTER_UNIT',
        unitId,
        blockBid: 'block-1',
        position: 0,
        page: 3,
      },
      {
        type: 'USER_PLAY',
      },
    ]);

    expect(state.activeUnitId).toBe(unitId);
    expect(state.mode).toBe('waiting_audio');
    expect(commandTypes(state)).toEqual(['SHOW_PAGE']);
  });

  it('plays active unit as soon as audio becomes ready while waiting', () => {
    const unitId = buildListenUnitId('block-1', 0);
    let state = runEvents(createInitialListenRuntimeState(), [
      {
        type: 'REGISTER_UNIT',
        unitId,
        blockBid: 'block-1',
        position: 0,
        page: 0,
      },
      {
        type: 'USER_PLAY',
      },
    ]);
    state = consumeAllCommands(state);
    state = reduceListenRuntime(state, {
      type: 'UNIT_AUDIO_READY',
      unitId,
    });

    expect(state.mode).toBe('playing');
    expect(commandTypes(state)).toEqual(['PLAY_UNIT_AUDIO']);
  });

  it('advances to next unit after active audio ends', () => {
    const firstUnitId = buildListenUnitId('block-1', 0);
    const secondUnitId = buildListenUnitId('block-2', 0);
    let state = runEvents(createInitialListenRuntimeState(), [
      {
        type: 'REGISTER_UNIT',
        unitId: firstUnitId,
        blockBid: 'block-1',
        position: 0,
        page: 0,
        hasAudio: true,
      },
      {
        type: 'REGISTER_UNIT',
        unitId: secondUnitId,
        blockBid: 'block-2',
        position: 0,
        page: 1,
        hasAudio: true,
      },
      {
        type: 'USER_PLAY',
      },
    ]);
    state = consumeAllCommands(state);
    state = reduceListenRuntime(state, {
      type: 'UNIT_AUDIO_ENDED',
      unitId: firstUnitId,
    });

    expect(state.activeUnitId).toBe(secondUnitId);
    expect(state.mode).toBe('playing');
    expect(commandTypes(state)).toEqual(['SHOW_PAGE', 'PLAY_UNIT_AUDIO']);
  });

  it('blocks playback on interaction and resumes after resolve', () => {
    const unitId = buildListenUnitId('block-1', 0);
    let state = runEvents(createInitialListenRuntimeState(), [
      {
        type: 'REGISTER_UNIT',
        unitId,
        blockBid: 'block-1',
        position: 0,
        page: 0,
        hasAudio: true,
      },
      {
        type: 'USER_PLAY',
      },
    ]);
    state = consumeAllCommands(state);

    state = reduceListenRuntime(state, {
      type: 'INTERACTION_OPENED',
      blockBid: 'interaction-1',
      page: 0,
    });
    expect(state.mode).toBe('interaction_blocked');
    expect(commandTypes(state)).toEqual(['PAUSE_AUDIO']);

    state = consumeAllCommands(state);
    state = reduceListenRuntime(state, {
      type: 'INTERACTION_RESOLVED',
      blockBid: 'interaction-1',
    });
    expect(state.mode).toBe('playing');
    expect(commandTypes(state)).toEqual(['PLAY_UNIT_AUDIO']);
  });

  it('ignores stale audio-ended events for inactive units', () => {
    const firstUnitId = buildListenUnitId('block-1', 0);
    const secondUnitId = buildListenUnitId('block-2', 0);
    let state = runEvents(createInitialListenRuntimeState(), [
      {
        type: 'REGISTER_UNIT',
        unitId: firstUnitId,
        blockBid: 'block-1',
        position: 0,
        page: 0,
        hasAudio: true,
      },
      {
        type: 'REGISTER_UNIT',
        unitId: secondUnitId,
        blockBid: 'block-2',
        position: 0,
        page: 1,
        hasAudio: true,
      },
      {
        type: 'USER_PLAY',
      },
      {
        type: 'UNIT_AUDIO_ENDED',
        unitId: firstUnitId,
      },
    ]);
    state = consumeAllCommands(state);
    expect(state.activeUnitId).toBe(secondUnitId);

    state = reduceListenRuntime(state, {
      type: 'UNIT_AUDIO_ENDED',
      unitId: firstUnitId,
    });
    expect(state.activeUnitId).toBe(secondUnitId);
    expect(state.pendingCommands).toHaveLength(0);
  });
});
