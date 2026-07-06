import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ProfileOnboardingModal from './ProfileOnboardingModal';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, string>) => {
      const translations: Record<string, string> = {
        'module.profileOnboarding.variableLabels.sys_user_background':
          '用户职业/背景',
        'module.profileOnboarding.variableLabels.sys_user_nickname': '用户昵称',
        'module.profileOnboarding.variableLabels.sys_user_style': '授课风格',
        'module.profileOnboarding.variablePrompt': '请填写 {variable}',
      };
      const text = translations[key] || key;
      return params
        ? text.replace(
            /\{([a-zA-Z0-9_]+)\}/g,
            (_, name: string) => params[name] ?? `{${name}}`,
          )
        : text;
    },
  }),
}));

const FLOW = [
  '欢迎来到课程。',
  '?[%{{sys_user_nickname}}...怎么称呼你？]',
  '选择一个你偏好的授课风格。',
  '?[%{{sys_user_style}} 简洁 | 详细]',
  '?[%{{sys_user_background}}...你的职业/背景是什么？]',
].join('\n');

describe('ProfileOnboardingModal', () => {
  test('collects variables and submits them at the end', async () => {
    const onComplete = jest.fn().mockResolvedValue(undefined);

    render(
      <ProfileOnboardingModal
        open
        markdownflow={FLOW}
        currentValues={{}}
        errorMessage=''
        submitting={false}
        onComplete={onComplete}
        onSkip={jest.fn()}
      />,
    );

    expect(screen.getByText('欢迎来到课程。')).toBeInTheDocument();
    expect(screen.getByText('怎么称呼你？')).toBeInTheDocument();

    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '小明' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.next' }),
    );

    fireEvent.click(screen.getByRole('button', { name: '简洁' }));
    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.next' }),
    );

    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '产品经理' },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.complete',
      }),
    );

    await waitFor(() => {
      expect(onComplete).toHaveBeenCalledWith({
        sys_user_nickname: '小明',
        sys_user_style: '简洁',
        sys_user_background: '产品经理',
      });
    });
  });

  test('renders a localized fallback prompt for choice-only variables', () => {
    render(
      <ProfileOnboardingModal
        open
        markdownflow={FLOW}
        currentValues={{}}
        errorMessage=''
        submitting={false}
        onComplete={jest.fn()}
        onSkip={jest.fn()}
      />,
    );

    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '小明' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.next' }),
    );

    expect(screen.getByText('请填写 授课风格')).toBeInTheDocument();
    expect(screen.queryByText(/{{variable}}/)).not.toBeInTheDocument();
  });

  test('submits skip without collecting variables', () => {
    const onSkip = jest.fn();

    render(
      <ProfileOnboardingModal
        open
        markdownflow={FLOW}
        currentValues={{}}
        errorMessage=''
        submitting={false}
        onComplete={jest.fn()}
        onSkip={onSkip}
      />,
    );

    fireEvent.click(
      screen.getByRole('button', { name: 'module.profileOnboarding.skip' }),
    );

    expect(onSkip).toHaveBeenCalledTimes(1);
  });

  test('keeps the dialog open when backend validation fails', () => {
    render(
      <ProfileOnboardingModal
        open
        markdownflow={FLOW}
        currentValues={{}}
        errorMessage='昵称包含风险词'
        submitting={false}
        onComplete={jest.fn()}
        onSkip={jest.fn()}
      />,
    );

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('昵称包含风险词')).toBeInTheDocument();
  });
});
