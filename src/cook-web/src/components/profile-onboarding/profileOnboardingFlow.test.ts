import {
  collectProfileOnboardingVariableKeys,
  parseProfileOnboardingFlow,
} from './profileOnboardingFlow';

const FLOW = [
  '欢迎来到课程。',
  '?[%{{sys_user_nickname}}...怎么称呼你？]',
  '选择一个你偏好的授课风格。',
  '?[%{{sys_user_style}} 简洁 | 详细]',
  '?[%{{sys_user_background}}...你的职业/背景是什么？]',
].join('\n');

describe('profile onboarding flow parser', () => {
  test('extracts static onboarding questions in order', () => {
    expect(parseProfileOnboardingFlow(FLOW)).toEqual([
      {
        id: 'sys_user_nickname-0',
        intro: '欢迎来到课程。',
        options: [],
        prompt: '怎么称呼你？',
        type: 'text',
        variableKey: 'sys_user_nickname',
      },
      {
        id: 'sys_user_style-1',
        intro: '选择一个你偏好的授课风格。',
        options: [
          { label: '简洁', value: '简洁' },
          { label: '详细', value: '详细' },
        ],
        prompt: '',
        type: 'choice',
        variableKey: 'sys_user_style',
      },
      {
        id: 'sys_user_background-2',
        intro: '',
        options: [],
        prompt: '你的职业/背景是什么？',
        type: 'text',
        variableKey: 'sys_user_background',
      },
    ]);
  });

  test('collects variable keys for client-side validation', () => {
    expect(collectProfileOnboardingVariableKeys(FLOW)).toEqual([
      'sys_user_nickname',
      'sys_user_style',
      'sys_user_background',
    ]);
  });
});
