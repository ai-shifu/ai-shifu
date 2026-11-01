import {
  ChatContentItemType as T,
  type ChatContentItem,
} from '@/types/chat-ui';
import {
  requiresInteractionRewind,
  updateInteractionItems,
} from './chat-interaction-rewind';

const items: ChatContentItem[] = [
  { element_bid: 'intro', type: T.CONTENT, content: 'Explains purpose' },
  {
    element_bid: 'q1',
    type: T.INTERACTION,
    content: '?[%{{purpose}} A|B]',
    user_input: 'A',
  },
  {
    element_bid: 'q2',
    type: T.INTERACTION,
    content: '?[%{{purpose}} A|B]',
    user_input: 'A',
  },
  { element_bid: 'later', type: T.CONTENT, content: 'Old result' },
];

it('keeps the exact question and prefix with repeated variable names', () => {
  const result = updateInteractionItems(
    items,
    { variableName: 'purpose', selectedValues: ['B'] },
    'q2',
    { truncateFollowingItems: true },
  );
  expect(result.index).toBe(2);
  expect(result.items).toEqual([
    items[0],
    items[1],
    { ...items[2], user_input: 'B', readonly: false },
  ]);
  expect(items[2].user_input).toBe('A');
});

it('uses exact element identity for controls without a variable', () => {
  const result = updateInteractionItems(
    items,
    { variableName: '', inputText: 'New answer' },
    'q1',
    { truncateFollowingItems: true },
  );
  expect(result.index).toBe(1);
  expect(result.items[1].user_input).toBe('New answer');
  expect(result.items[0]).toBe(items[0]);
});

it('does not match ambiguous variables or empty names when the anchor is missing', () => {
  for (const variableName of ['', 'purpose']) {
    expect(
      updateInteractionItems(
        items,
        { variableName, inputText: 'New' },
        'missing',
        { truncateFollowingItems: true },
      ),
    ).toEqual({ items, index: -1 });
  }
});

it('retains later controls when answering a pending queue without a rewind', () => {
  expect(
    updateInteractionItems(items, { selectedValues: ['B'] }, 'q1', {
      truncateFollowingItems: false,
    }).items,
  ).toHaveLength(4);
});

it('ignores helper rows when detecting an earlier answer and preserves helpers only when requested', () => {
  const helpers: ChatContentItem[] = [
    {
      element_bid: 'helper',
      parent_element_bid: 'q1',
      type: T.LIKE_STATUS,
      content: '',
    },
  ];
  const list = [...items.slice(0, 2), ...helpers];
  expect(requiresInteractionRewind(list, 'q1')).toBe(false);
  expect(requiresInteractionRewind(items, 'q1')).toBe(true);
  expect(
    updateInteractionItems(list, { selectedValues: ['B'] }, 'q1', {
      truncateFollowingItems: true,
      preserveHelpers: true,
    }).items.at(-1),
  ).toBe(helpers[0]);
  expect(
    updateInteractionItems(list, { selectedValues: ['B'] }, 'q1', {
      truncateFollowingItems: true,
    }).items,
  ).toHaveLength(2);
});

it('ignores error rows when retrying the current question after a failed stream', () => {
  const list: ChatContentItem[] = [
    items[0],
    items[1],
    { element_bid: 'business-error', type: T.ERROR, content: 'Request failed' },
  ];
  expect(requiresInteractionRewind(list, 'q1')).toBe(false);
  expect(requiresInteractionRewind([...list, items[3]], 'q1')).toBe(true);
});
