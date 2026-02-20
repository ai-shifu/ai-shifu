import { act, renderHook } from '@testing-library/react';
import {
  buildListenUnitId,
  useListenOrchestrator,
} from '@/c-utils/listen-domain';

describe('listen-domain orchestrator hook', () => {
  it('dispatches events and exposes pending commands', () => {
    const unitId = buildListenUnitId('block-1', 0);
    const { result } = renderHook(() => useListenOrchestrator());

    act(() => {
      result.current.dispatchEvents([
        {
          type: 'REGISTER_UNIT',
          unitId,
          blockBid: 'block-1',
          position: 0,
          page: 2,
        },
        {
          type: 'USER_PLAY',
        },
      ]);
    });

    expect(result.current.state.activeUnitId).toBe(unitId);
    expect(result.current.state.mode).toBe('waiting_audio');
    expect(result.current.getNextCommand()?.type).toBe('SHOW_PAGE');

    act(() => {
      result.current.consumeCommands(1);
    });
    expect(result.current.getNextCommand()).toBeNull();
  });

  it('resets state after reset command', () => {
    const unitId = buildListenUnitId('block-2', 0);
    const { result } = renderHook(() => useListenOrchestrator());

    act(() => {
      result.current.dispatchEvent({
        type: 'REGISTER_UNIT',
        unitId,
        blockBid: 'block-2',
        position: 0,
        page: 0,
        hasAudio: true,
      });
      result.current.dispatchEvent({
        type: 'USER_PLAY',
      });
    });

    expect(result.current.state.unitsInOrder).toHaveLength(1);
    expect(result.current.state.pendingCommands.length).toBeGreaterThan(0);

    act(() => {
      result.current.reset();
    });

    expect(result.current.state.unitsInOrder).toHaveLength(0);
    expect(result.current.state.activeUnitId).toBeNull();
    expect(result.current.state.pendingCommands).toHaveLength(0);
    expect(result.current.state.mode).toBe('idle');
  });
});
