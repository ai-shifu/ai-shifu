import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';
import { buildReadModeItemsWithAskState } from './readModeItems';

describe('readModeItems', () => {
  it('converts finalized listen mode items into history-like read mode items', () => {
    const items: ChatContentItem[] = [
      {
        type: ChatContentItemType.CONTENT,
        element_bid: 'content-1',
        content: 'Finished text',
        element_type: 'text',
        shouldUseTypewriter: true,
        shouldRenderAsHistoryInReadMode: true,
      },
    ];

    const [readModeItem] = buildReadModeItemsWithAskState({
      items,
      askListByAnchorElementBid: {},
      mobileStyle: false,
    });

    expect(readModeItem?.isHistory).toBe(true);
    expect(readModeItem?.shouldUseTypewriter).toBe(false);
  });
});
