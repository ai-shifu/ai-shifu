import { getReadingFollowUpAnchors } from './reading-follow-up-anchors';
import {
  ChatContentItemType as Kind,
  type ChatContentItem,
} from '@/types/chat-ui';
test('only finalized persistent teaching has a reading boundary', () => {
  const items: ChatContentItem[] = [
    {
      element_bid: 'history',
      type: Kind.CONTENT,
      content: 'Earlier teaching',
      isHistory: true,
    },
    {
      element_bid: 'complete',
      type: Kind.CONTENT,
      content: 'Completed teaching',
    },
    { element_bid: '', type: Kind.LIKE_STATUS, parent_element_bid: 'complete' },
    {
      element_bid: 'streaming',
      type: Kind.CONTENT,
      content: 'Still streaming',
    },
    {
      element_bid: 'interaction',
      type: Kind.INTERACTION,
      content: 'Question',
      isHistory: true,
    },
    {
      element_bid: 'loading',
      type: Kind.CONTENT,
      content: 'Loading',
      isHistory: true,
    },
    {
      element_bid: 'plain-text',
      type: Kind.CONTENT,
      content: 'Persisted plain text',
      isHistory: true,
      is_renderable: false,
    },
    {
      element_bid: 'visual',
      type: Kind.CONTENT,
      content: '<svg />',
      element_type: 'svg',
      isHistory: true,
      is_marker: true,
    },
    {
      element_bid: 'empty',
      type: Kind.CONTENT,
      content: '<custom-button-after-content>Ask</custom-button-after-content>',
      isHistory: true,
    },
  ];
  expect([...getReadingFollowUpAnchors(items)]).toEqual([
    'history',
    'complete',
    'plain-text',
    'visual',
  ]);
});
