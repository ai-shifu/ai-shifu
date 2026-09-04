import { liveFollowUpMessageId } from '@/lib/liveFollowUpMessageIds';
import type {
  LiveVoiceFollowUpHistoryTurn,
  LiveVoiceTranscript,
} from '@/components/live-follow-up/useLiveVoiceFollowUp';
import type { AskMessage } from './askState';

export type LiveAskTranscriptUpdate = LiveVoiceTranscript & {
  sessionBid: string;
  outlineBid: string;
  anchorElementBid: string;
};

export const upsertLiveAskTranscript = (
  previous: AskMessage[],
  update: LiveAskTranscriptUpdate,
): AskMessage[] => {
  const elementBid = liveFollowUpMessageId(
    update.sessionBid,
    update.turnIndex,
    update.role,
  );
  const index = previous.findIndex(
    message => message.element_bid === elementBid,
  );
  const message: AskMessage = {
    ...previous[index],
    type: update.role === 'user' ? 'ask' : 'answer',
    content: update.text,
    element_bid: elementBid,
    isStreaming: !update.final,
    shouldUseTypewriter: false,
    interaction_mode: 'live_voice',
    live_session_bid: update.sessionBid,
    live_turn_index: update.turnIndex,
  };
  if (index < 0) {
    const before = previous.findIndex(
      item =>
        item.live_session_bid === update.sessionBid &&
        ((item.live_turn_index ?? 0) > update.turnIndex ||
          (item.live_turn_index === update.turnIndex &&
            update.role === 'user' &&
            item.type === 'answer')),
    );
    const next = [...previous];
    next.splice(before < 0 ? next.length : before, 0, message);
    return next;
  }
  return previous.map((item, itemIndex) =>
    itemIndex === index ? message : item,
  );
};

export const finalizeLiveAskTurn = (
  previous: AskMessage[],
  turn: LiveVoiceFollowUpHistoryTurn,
): AskMessage[] => {
  const userId = liveFollowUpMessageId(turn.sessionBid, turn.turnIndex, 'user');
  const answerId = liveFollowUpMessageId(
    turn.sessionBid,
    turn.turnIndex,
    'assistant',
  );
  if (!turn.userTranscript.trim()) {
    return previous.filter(
      message =>
        message.element_bid !== userId && message.element_bid !== answerId,
    );
  }
  let next = previous;
  for (const role of ['user', 'assistant'] as const) {
    next = upsertLiveAskTranscript(next, {
      ...turn,
      role,
      final: true,
      text: role === 'user' ? turn.userTranscript : turn.assistantTranscript,
    });
  }
  return next.map(message =>
    message.element_bid === userId || message.element_bid === answerId
      ? {
          ...message,
          interrupted: turn.interrupted,
          element_bid:
            message.type === 'ask'
              ? turn.askElementBid || userId
              : turn.answerElementBid || answerId,
        }
      : message,
  );
};
