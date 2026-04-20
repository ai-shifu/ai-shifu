import {
  appendCustomButtonAfterContent,
  hasCustomButtonAfterContent,
  inheritCustomButtonAfterContent,
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

  it('detects the follow-up button markup in content', () => {
    const contentWithButton = appendCustomButtonAfterContent(
      'Lesson summary',
      buttonMarkup,
    );

    expect(hasCustomButtonAfterContent(contentWithButton)).toBe(true);
    expect(hasCustomButtonAfterContent('Lesson summary')).toBe(false);
  });

  it('inherits the follow-up button from previous finalized content', () => {
    const previousContent = appendCustomButtonAfterContent(
      'Lesson summary',
      buttonMarkup,
    );

    expect(
      inheritCustomButtonAfterContent({
        nextContent: 'Updated lesson summary',
        previousContent,
        buttonMarkup,
      }),
    ).toBe(
      appendCustomButtonAfterContent('Updated lesson summary', buttonMarkup),
    );
  });
});
