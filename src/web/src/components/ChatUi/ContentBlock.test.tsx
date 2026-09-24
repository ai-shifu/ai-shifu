import { render, screen } from '@testing-library/react';
import ContentBlock from './ContentBlock';
import { ChatContentItemType, type ChatContentItem } from '@/types/chatUi';

jest.mock('@/api/studyV2', () => ({
  LESSON_FEEDBACK_INTERACTION_MARKER: 'sys_lesson_feedback_score',
  SYS_INTERACTION_TYPE: {
    NEXT_CHAPTER: '_sys_next_chapter',
    PAY: '_sys_pay',
    LOGIN: '_sys_login',
  },
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'es-ES', resolvedLanguage: 'es-ES' },
  }),
}));

jest.mock('markdown-flow-ui/renderer', () => ({
  ContentRender: ({
    content,
    locale,
    lang,
  }: {
    content: string;
    locale: string;
    lang: string;
  }) => (
    <div
      data-testid='course-content'
      data-locale={locale}
      lang={lang}
    >
      {content}
    </div>
  ),
}));

const guideContent: ChatContentItem = {
  element_bid: 'guide-content',
  type: ChatContentItemType.CONTENT,
  content: 'Create your first course',
};
const onSend = jest.fn();

const renderContent = (contentLanguage?: string) =>
  render(
    <ContentBlock
      item={guideContent}
      mobileStyle={false}
      blockBid='guide-content'
      contentLanguage={contentLanguage}
      onSend={onSend}
    />,
  );

describe('ContentBlock content language', () => {
  it('keeps the English guide body marked as English under a Spanish UI', () => {
    renderContent('en-US');

    expect(screen.getByTestId('course-content')).toHaveAttribute(
      'data-locale',
      'en-US',
    );
    expect(screen.getByTestId('course-content')).toHaveAttribute(
      'lang',
      'en-US',
    );
  });

  it('preserves an explicitly known Spanish content language', () => {
    renderContent('es-ES');

    expect(screen.getByTestId('course-content')).toHaveAttribute(
      'data-locale',
      'en-US',
    );
    expect(screen.getByTestId('course-content')).toHaveAttribute(
      'lang',
      'es-ES',
    );
  });

  it('does not infer unknown authored content language from the Spanish UI', () => {
    const view = renderContent();

    expect(screen.getByTestId('course-content')).toHaveAttribute('lang', '');

    view.rerender(
      <ContentBlock
        item={guideContent}
        mobileStyle={false}
        blockBid='guide-content'
        contentLanguage='en-US'
        onSend={onSend}
      />,
    );

    expect(screen.getByTestId('course-content')).toHaveAttribute(
      'lang',
      'en-US',
    );
  });
});
