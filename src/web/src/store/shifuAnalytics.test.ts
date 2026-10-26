import {
  buildOutlineCreateAnalytics,
  OUTLINE_CREATE_EVENT,
} from './shifuAnalytics';

describe('outline create analytics', () => {
  it('uses the stable event name and an ID-only payload', () => {
    const payload = buildOutlineCreateAnalytics({
      shifuBid: 'course-1',
      outlineBid: 'lesson-1',
      parentBid: 'chapter-1',
    });

    expect(OUTLINE_CREATE_EVENT).toBe('creator_outline_create');
    expect(payload).toEqual({
      shifu_bid: 'course-1',
      outline_bid: 'lesson-1',
      parent_bid: 'chapter-1',
    });
    expect(payload).not.toHaveProperty('outline_name');
    expect(payload).not.toHaveProperty('name');
    expect(payload).not.toHaveProperty('description');
  });
});
