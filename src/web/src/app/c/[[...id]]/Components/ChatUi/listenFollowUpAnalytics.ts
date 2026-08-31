export const LISTEN_FOLLOW_UP_ATTEMPT_EVENT =
  'learner_listen_follow_up_attempt' as const;
export const LISTEN_FOLLOW_UP_RESULT_EVENT =
  'learner_listen_follow_up_result' as const;

export type ListenFollowUpSurface = 'desktop' | 'mobile' | 'mobile_fullscreen';
export type ListenFollowUpOutcome = 'success' | 'failed' | 'cancelled';

export const buildListenFollowUpAttemptAnalytics = ({
  shifuBid,
  outlineBid,
  surface,
}: {
  shifuBid: string;
  outlineBid: string;
  surface: ListenFollowUpSurface;
}) => ({
  shifu_bid: shifuBid,
  outline_bid: outlineBid,
  surface,
});

export const buildListenFollowUpResultAnalytics = ({
  shifuBid,
  outlineBid,
  surface,
  outcome,
}: {
  shifuBid: string;
  outlineBid: string;
  surface: ListenFollowUpSurface;
  outcome: ListenFollowUpOutcome;
}) => ({
  ...buildListenFollowUpAttemptAnalytics({ shifuBid, outlineBid, surface }),
  outcome,
});
