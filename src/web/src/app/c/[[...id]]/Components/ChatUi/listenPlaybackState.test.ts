import {
  buildListenMarkerSequenceKey,
  reconcileListenPlaybackStepCount,
  resetListenPlaybackStateForSequence,
  resolveCurrentStepAudioCompletion,
  type ListenPlaybackState,
} from './listenPlaybackState';

describe('listenPlaybackState', () => {
  const buildPlaybackState = (
    overrides: Partial<ListenPlaybackState> = {},
  ): ListenPlaybackState => ({
    currentStepIndex: 1,
    totalStepCount: 3,
    currentStepHasAudio: true,
    currentStepHasBlockingInteraction: false,
    hasCompletedCurrentStepAudio: true,
    isAudioPlaying: false,
    isAudioWaiting: false,
    ...overrides,
  });

  it('uses marker identity instead of only marker count for sequence changes', () => {
    const previousSequenceKey = buildListenMarkerSequenceKey([
      {
        type: 'text',
        sequence_number: 1,
        blockBid: 'marker-a',
        page: 0,
      } as any,
      {
        type: 'text',
        sequence_number: 2,
        blockBid: 'marker-b',
        page: 1,
      } as any,
    ]);
    const nextSequenceKey = buildListenMarkerSequenceKey([
      {
        type: 'text',
        sequence_number: 1,
        blockBid: 'marker-x',
        page: 0,
      } as any,
      {
        type: 'text',
        sequence_number: 2,
        blockBid: 'marker-y',
        page: 1,
      } as any,
    ]);

    expect(previousSequenceKey).not.toBe(nextSequenceKey);
  });

  it('distinguishes id-less marker sequences by fallback identity', () => {
    const previousSequenceKey = buildListenMarkerSequenceKey([
      {
        type: 'text',
        sequence_number: 1,
        page: 0,
        content: 'First outline marker',
      } as any,
      {
        type: 'text',
        sequence_number: 2,
        page: 1,
        content: 'Second outline marker',
      } as any,
    ]);
    const nextSequenceKey = buildListenMarkerSequenceKey([
      {
        type: 'text',
        sequence_number: 1,
        page: 0,
        content: 'Replacement marker',
      } as any,
      {
        type: 'text',
        sequence_number: 2,
        page: 1,
        content: 'Second outline marker',
      } as any,
    ]);

    expect(previousSequenceKey).not.toBe(nextSequenceKey);
  });

  it('preserves the current step while only the marker count changes', () => {
    const nextState = reconcileListenPlaybackStepCount(buildPlaybackState(), 4);

    expect(nextState.currentStepIndex).toBe(1);
    expect(nextState.totalStepCount).toBe(4);
    expect(nextState.hasCompletedCurrentStepAudio).toBe(true);
  });

  it('clamps the current step when the marker count shrinks', () => {
    const nextState = reconcileListenPlaybackStepCount(
      buildPlaybackState({ currentStepIndex: 2 }),
      2,
    );

    expect(nextState.currentStepIndex).toBe(1);
    expect(nextState.totalStepCount).toBe(2);
  });

  it('keeps the initial unresolved step index when count updates before step sync', () => {
    const nextState = reconcileListenPlaybackStepCount(
      buildPlaybackState({ currentStepIndex: -1, totalStepCount: 1 }),
      3,
    );

    expect(nextState.currentStepIndex).toBe(-1);
    expect(nextState.totalStepCount).toBe(3);
  });

  it('keeps the same object when playback is already reset for the marker sequence', () => {
    const resetState = buildPlaybackState({
      currentStepIndex: -1,
      totalStepCount: 3,
      currentStepHasAudio: false,
      currentStepHasBlockingInteraction: false,
      hasCompletedCurrentStepAudio: false,
      isAudioPlaying: false,
      isAudioWaiting: false,
    });

    const nextState = resetListenPlaybackStateForSequence(resetState, 3);

    expect(nextState).toBe(resetState);
  });

  it('resets playback only when marker sequence state still carries old step data', () => {
    const nextState = resetListenPlaybackStateForSequence(
      buildPlaybackState({
        currentStepIndex: 1,
        totalStepCount: 2,
        currentStepHasAudio: true,
        hasCompletedCurrentStepAudio: true,
        isAudioPlaying: true,
      }),
      3,
    );

    expect(nextState).toEqual({
      currentStepIndex: -1,
      totalStepCount: 3,
      currentStepHasAudio: false,
      currentStepHasBlockingInteraction: false,
      hasCompletedCurrentStepAudio: false,
      isAudioPlaying: false,
      isAudioWaiting: false,
    });
  });

  it('resets completed audio when a marker gains audio after initially having none', () => {
    const nextCompletedState = resolveCurrentStepAudioCompletion({
      previousStepHasAudio: false,
      nextStepHasAudio: true,
      previousCompleted: true,
      isSameMarkerStep: true,
    });

    expect(nextCompletedState).toBe(false);
  });

  it('preserves completed audio only when the same marker keeps the same audio presence', () => {
    const nextCompletedState = resolveCurrentStepAudioCompletion({
      previousStepHasAudio: true,
      nextStepHasAudio: true,
      previousCompleted: true,
      isSameMarkerStep: true,
    });

    expect(nextCompletedState).toBe(true);
  });
});
