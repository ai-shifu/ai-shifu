import {
  appendCustomButtonAfterContent,
  hasInteractionResponse,
  stripCustomButtonAfterContent,
} from '@/app/c/[[...id]]/Components/ChatUi/chatUiUtils';

describe('chatUiUtils', () => {
  describe('hasInteractionResponse', () => {
    it('returns false for empty interaction payload', () => {
      expect(hasInteractionResponse(null)).toBe(false);
      expect(hasInteractionResponse(undefined)).toBe(false);
      expect(hasInteractionResponse({})).toBe(false);
    });

    it('detects selected values response', () => {
      expect(
        hasInteractionResponse({
          defaultSelectedValues: ['  ', 'option-a'],
        }),
      ).toBe(true);
    });

    it('detects button and input responses', () => {
      expect(
        hasInteractionResponse({
          defaultButtonText: 'Confirm',
        }),
      ).toBe(true);
      expect(
        hasInteractionResponse({
          defaultInputText: 'answer',
        }),
      ).toBe(true);
    });
  });

  describe('appendCustomButtonAfterContent', () => {
    const buttonMarkup =
      '<custom-button-after-content><button>ask</button></custom-button-after-content>';

    it('appends markup once', () => {
      const content = 'hello';
      const next = appendCustomButtonAfterContent(content, buttonMarkup);
      expect(next).toContain(buttonMarkup);
      expect(appendCustomButtonAfterContent(next, buttonMarkup)).toBe(next);
    });
  });

  describe('stripCustomButtonAfterContent', () => {
    it('strips ask button wrapper and keeps markdown body', () => {
      const content =
        'hello\n<custom-button-after-content><button>ask</button></custom-button-after-content>';
      expect(stripCustomButtonAfterContent(content)).toBe('hello');
    });
  });
});
