import {
  finalizeLiveAskTurn,
  upsertLiveAskTranscript,
} from './liveFollowUpAskHistory';
import { normalizeAskMessageList } from './askState';
import { useAskStateStore } from './useAskStateStore';
import { liveFollowUpMessageId } from '@/lib/liveFollowUpMessageIds';

const scope = {
  sessionBid: 'session-1',
  outlineBid: 'lesson-1',
  anchorElementBid: 'anchor-1',
  turnIndex: 1,
};

it('matches fixed UUIDv5 vectors from the backend persistence contract', () => {
  expect(liveFollowUpMessageId('session-1', 1, 'user')).toBe(
    '0f143140-2eb8-5e35-b7b2-c1d7850617c3',
  );
  expect(liveFollowUpMessageId('session-1', 1, 'assistant')).toBe(
    '6ec139dd-be12-5c03-a343-cccdcc847328',
  );
});

it('uses stable backend-compatible identities and orders unordered transcripts', () => {
  const answer = {
    ...scope,
    role: 'assistant' as const,
    text: 'Partial',
    final: false,
  };
  let list = upsertLiveAskTranscript([], answer);
  list = upsertLiveAskTranscript(list, {
    ...scope,
    role: 'user',
    text: 'Question',
    final: true,
  });
  const userId = liveFollowUpMessageId(scope.sessionBid, 1, 'user');
  const answerId = liveFollowUpMessageId(scope.sessionBid, 1, 'assistant');
  expect(list.map(item => item.type)).toEqual(['ask', 'answer']);
  expect(list.map(item => item.element_bid)).toEqual([userId, answerId]);
  list = finalizeLiveAskTurn(list, {
    ...scope,
    userTranscript: 'Question',
    assistantTranscript: 'Played',
    interrupted: true,
  });
  list = finalizeLiveAskTurn(list, {
    ...scope,
    userTranscript: 'Question',
    assistantTranscript: 'Played',
    interrupted: true,
    askElementBid: userId,
    answerElementBid: answerId,
  });
  expect(list).toHaveLength(2);
  expect(list[1]).toMatchObject({
    content: 'Played',
    element_bid: answerId,
    isStreaming: false,
    shouldUseTypewriter: false,
    interrupted: true,
  });
});

it('removes interim-only speech instead of manufacturing history', () => {
  const list = upsertLiveAskTranscript([], {
    ...scope,
    role: 'user',
    text: 'Unconfirmed',
    final: false,
  });
  expect(
    finalizeLiveAskTurn(list, {
      ...scope,
      userTranscript: '',
      assistantTranscript: '',
      interrupted: true,
    }),
  ).toEqual([]);
});

it('preserves saved identity on history hydration and rejects late writes into another lesson', () => {
  const store = useAskStateStore.getState();
  store.clearLessonScope();
  store.ensureLessonScope(scope.outlineBid);
  const list = finalizeLiveAskTurn([], {
    ...scope,
    userTranscript: 'Typed question',
    assistantTranscript: '',
    interrupted: true,
  });
  store.setAskList(scope.anchorElementBid, list, scope.outlineBid);
  store.hydrateAskList(
    scope.anchorElementBid,
    normalizeAskMessageList(
      list.map(item => ({
        type: item.type,
        content: item.content,
        element_bid: item.element_bid,
        payload: {
          interaction_mode: 'live_voice',
          live_session_bid: scope.sessionBid,
          live_turn_index: 1,
          interrupted: true,
        },
      })),
    ),
  );
  expect(
    useAskStateStore.getState().askListByAnchorElementBid[
      scope.anchorElementBid
    ],
  ).toHaveLength(2);
  store.ensureLessonScope('lesson-2');
  store.setAskList(scope.anchorElementBid, list, scope.outlineBid);
  expect(useAskStateStore.getState().askListByAnchorElementBid).toEqual({});
});
