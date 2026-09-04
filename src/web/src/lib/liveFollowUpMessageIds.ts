import { v5 as uuidv5 } from 'uuid';

// Mirrors live_follow_up_persistence.deterministic_live_turn_bid. These IDs
// are render identities, never authorization or proof of durable persistence.
const LIVE_TURN_NAMESPACE = '53108c61-7df0-5264-8f6c-f1438f13fd2a';

export const liveFollowUpMessageId = (
  sessionBid: string,
  turnIndex: number,
  role: 'user' | 'assistant',
) =>
  uuidv5(
    `ai-shifu:gemini-live:${sessionBid}:${turnIndex}:${role === 'user' ? 'ask' : 'answer'}-element`,
    LIVE_TURN_NAMESPACE,
  );
