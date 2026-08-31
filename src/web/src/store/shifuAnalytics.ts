export const OUTLINE_CREATE_EVENT = 'creator_outline_create';

type OutlineCreateAnalyticsInput = {
  shifuBid?: string | null;
  outlineBid?: string | null;
  parentBid?: string | null;
};

export const buildOutlineCreateAnalytics = ({
  shifuBid,
  outlineBid,
  parentBid,
}: OutlineCreateAnalyticsInput) => ({
  shifu_bid: shifuBid || '',
  outline_bid: outlineBid || '',
  parent_bid: parentBid || '',
});
