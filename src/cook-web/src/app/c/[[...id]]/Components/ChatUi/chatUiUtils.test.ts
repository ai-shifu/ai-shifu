import {
  appendCustomButtonAfterContent,
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
});
