jest.mock('@/c-api/studyV2', () => ({
  SYS_INTERACTION_TYPE: {
    NEXT_CHAPTER: '_sys_next_chapter',
    PAY: '_sys_pay',
    LOGIN: '_sys_login',
  },
}));

import { localizeSystemInteractionContent } from './system-interaction';

const translate = (key: string) =>
  ({
    'server.learn.nextChapterButton': '下一节',
    'server.order.checkout': '去支付',
    'server.user.login': '登录',
  })[key] ?? key;

describe('localizeSystemInteractionContent', () => {
  it('localizes persisted next-chapter labels from the runtime language', () => {
    expect(
      localizeSystemInteractionContent('?[Next//_sys_next_chapter]', translate),
    ).toBe('?[下一节//_sys_next_chapter]');
  });

  it('keeps the system action while replacing only the label', () => {
    expect(
      localizeSystemInteractionContent(
        'before ?[Suivant//_sys_next_chapter] after',
        translate,
      ),
    ).toBe('before ?[下一节//_sys_next_chapter] after');
  });

  it('does not rewrite non-system interactions', () => {
    expect(
      localizeSystemInteractionContent('?[Next//custom_action]', translate),
    ).toBe('?[Next//custom_action]');
  });

  it('localizes persisted pay and login system labels from the runtime language', () => {
    expect(
      localizeSystemInteractionContent('?[Pay//_sys_pay]', translate),
    ).toBe('?[去支付//_sys_pay]');
    expect(
      localizeSystemInteractionContent('?[Login//_sys_login]', translate),
    ).toBe('?[登录//_sys_login]');
  });
});
