import {
  appendCustomButtonAfterContent,
  resolvePreviousActionableItem,
  shouldShowMobileAskButtonForReadContent,
  syncCustomButtonAfterContent,
} from './chatUiUtils';

describe('chatUiUtils', () => {
  const buttonMarkup =
    '<custom-button-after-content><span>Ask</span></custom-button-after-content>';

  it('re-appends the follow-up button when read mode restores mobile content', () => {
    const contentWithoutButton = 'Lesson summary';

    expect(
      syncCustomButtonAfterContent({
        content: contentWithoutButton,
        buttonMarkup,
        shouldShowButton: true,
      }),
    ).toBe(appendCustomButtonAfterContent(contentWithoutButton, buttonMarkup));
  });

  it('removes the follow-up button when listen mode content is rendered', () => {
    const contentWithButton = appendCustomButtonAfterContent(
      'Lesson summary',
      buttonMarkup,
    );

    expect(
      syncCustomButtonAfterContent({
        content: contentWithButton,
        buttonMarkup,
        shouldShowButton: false,
      }),
    ).toBe('Lesson summary');
  });

  it('hides the mobile follow-up button for loading placeholders', () => {
    expect(
      shouldShowMobileAskButtonForReadContent({
        item: {
          element_bid: 'loading',
          type: 'content',
        },
      }),
    ).toBe(false);
  });

  it('hides the mobile follow-up button for content after an interaction', () => {
    const items = [
      {
        element_bid: 'interaction-1',
        type: 'interaction',
      },
      {
        parent_element_bid: 'interaction-1',
        type: 'likeStatus',
      },
      {
        element_bid: 'content-1',
        type: 'content',
      },
    ];
    const previousActionableItem = resolvePreviousActionableItem(items, 2);

    expect(
      shouldShowMobileAskButtonForReadContent({
        item: items[2],
        previousActionableItem,
      }),
    ).toBe(false);
  });

  it('keeps the mobile follow-up button for regular read-mode content', () => {
    const items = [
      {
        element_bid: 'content-0',
        type: 'content',
      },
      {
        parent_element_bid: 'content-0',
        type: 'likeStatus',
      },
      {
        element_bid: 'content-1',
        type: 'content',
      },
    ];
    const previousActionableItem = resolvePreviousActionableItem(items, 2);

    expect(
      shouldShowMobileAskButtonForReadContent({
        item: items[2],
        previousActionableItem,
      }),
    ).toBe(true);
  });
});
