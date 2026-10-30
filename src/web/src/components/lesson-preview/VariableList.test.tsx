import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import VariableList from './VariableList';
import styles from './VariableList.module.scss';

const mockTranslations: Record<string, Record<string, string>> = {
  'zh-CN': {
    'module.shifu.previewArea.personalInfoPlaceholder': '填写{label}',
    'module.shifu.previewArea.variablesPlaceholder': '填写模拟回答',
    'module.shifu.previewArea.variablesTitle': '记忆',
    'module.shifu.previewArea.variablesHideUnused': '隐藏未使用项',
    'module.shifu.previewArea.variablesRestoreHidden': '显示全部',
    'module.shifu.previewArea.variablesHideSingleConfirmTitle': '隐藏此项',
    'module.shifu.previewArea.systemVariableLabels.nickname': '学生昵称',
    'module.shifu.previewArea.systemVariableLabels.background': '学生背景偏好',
    'module.shifu.previewArea.systemVariableLabels.input': '最新输入',
    'module.shifu.previewArea.systemVariableLabels.language': '授课语言',
  },
  'en-US': {
    'module.shifu.previewArea.personalInfoPlaceholder': 'Enter {label}',
    'module.shifu.previewArea.variablesPlaceholder': 'Enter a simulated answer',
    'module.shifu.previewArea.variablesTitle': 'Memory',
    'module.shifu.previewArea.systemVariableLabels.nickname':
      'Student nickname',
    'module.shifu.previewArea.systemVariableLabels.background':
      'Student background and preferences',
    'module.shifu.previewArea.systemVariableLabels.input': 'Latest input',
    'module.shifu.previewArea.systemVariableLabels.language':
      'Teaching language',
  },
};
let mockLanguage = 'zh-CN';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string>) => {
      const template = mockTranslations[mockLanguage]?.[key] ?? key;
      return Object.entries(values ?? {}).reduce(
        (result, [name, value]) => result.replace(`{${name}}`, value),
        template,
      );
    },
  }),
}));

describe('VariableList system variable labels', () => {
  beforeEach(() => {
    mockLanguage = 'zh-CN';
  });

  test('keeps localized labels on hover and exposes no raw system keys', () => {
    const onChange = jest.fn();
    const variables = {
      sys_user_nickname: 'Learner',
      sys_user_background: 'Teacher',
      sys_user_input: 'Question',
      sys_user_language: 'Chinese',
    };

    const { container } = render(
      <VariableList
        variables={variables}
        systemVariableKeys={Object.keys(variables)}
        onChange={onChange}
      />,
    );

    [
      ['学生昵称', 'sys_user_nickname'],
      ['学生背景偏好', 'sys_user_background'],
      ['最新输入', 'sys_user_input'],
      ['授课语言', 'sys_user_language'],
    ].forEach(([label, rawKey]) => {
      const nameCell = screen.getByText(label);
      expect(nameCell).toHaveClass(styles.name);
      expect(nameCell).not.toHaveAttribute('title');
      expect(nameCell).not.toHaveAttribute('tabindex');
      expect(screen.getByPlaceholderText(`填写${label}`)).toHaveValue(
        variables[rawKey as keyof typeof variables],
      );
      const input = screen.getByRole('textbox', { name: label });
      input.focus();
      expect(input).toHaveFocus();
      fireEvent.mouseEnter(nameCell);
      expect(nameCell).toHaveTextContent(label);
      expect(screen.queryByText(rawKey)).not.toBeInTheDocument();
      expect(screen.queryByTitle(rawKey)).not.toBeInTheDocument();
      expect(
        screen.queryByLabelText(new RegExp(rawKey)),
      ).not.toBeInTheDocument();
      fireEvent.mouseLeave(nameCell);
    });
    expect(container.textContent).not.toContain('sys_user_');

    fireEvent.change(screen.getByDisplayValue('Learner'), {
      target: { value: 'Alex' },
    });
    expect(onChange).toHaveBeenCalledWith('sys_user_nickname', 'Alex');
  });

  test('preserves authored keys and uses a localized fallback for unknown system fields', () => {
    const onChange = jest.fn();
    render(
      <VariableList
        variables={{
          custom_topic: 'Testing',
          'What would you like to learn?': 'AI',
          sys_user_future: 'Future',
          constructor: 'Custom class',
        }}
        systemVariableKeys={['sys_user_future']}
        onChange={onChange}
      />,
    );

    const customNameCell = screen.getByText('custom_topic').closest('div');
    expect(customNameCell).toHaveClass(styles.name);
    expect(screen.queryByText('sys_user_future')).not.toBeInTheDocument();
    expect(screen.queryByTitle('sys_user_future')).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '记忆' })).toHaveValue('Future');
    expect(screen.getByPlaceholderText('填写记忆')).toHaveValue('Future');
    expect(screen.getByRole('textbox', { name: 'constructor' })).toHaveValue(
      'Custom class',
    );
    expect(screen.getAllByPlaceholderText('填写模拟回答')).toHaveLength(3);

    fireEvent.change(screen.getByDisplayValue('AI'), {
      target: { value: 'Practical AI skills' },
    });
    expect(onChange).toHaveBeenCalledWith(
      'What would you like to learn?',
      'Practical AI skills',
    );
    fireEvent.change(screen.getByDisplayValue('Future'), {
      target: { value: 'Updated' },
    });
    expect(onChange).toHaveBeenCalledWith('sys_user_future', 'Updated');
  });

  test('preserves a custom memory label when a system key has the same name', () => {
    const onChange = jest.fn();
    const onHideVariable = jest.fn();
    render(
      <VariableList
        variables={{ avatar: 'Custom answer' }}
        systemVariableKeys={['avatar']}
        customVariableKeys={['avatar']}
        unusedVariableKeys={['avatar']}
        onChange={onChange}
        onHideVariable={onHideVariable}
      />,
    );

    expect(screen.getByText('avatar')).not.toHaveAttribute('title');
    const input = screen.getByRole('textbox', { name: 'avatar' });
    expect(input).toHaveValue('Custom answer');
    expect(input).toHaveAttribute('placeholder', '填写模拟回答');
    expect(screen.queryByPlaceholderText('填写记忆')).not.toBeInTheDocument();

    fireEvent.change(input, { target: { value: 'Updated answer' } });
    expect(onChange).toHaveBeenCalledWith('avatar', 'Updated answer');
    fireEvent.click(screen.getByRole('button', { name: '隐藏此项' }));
    expect(onHideVariable).toHaveBeenCalledWith('avatar');
  });

  test.each([
    { systemVariableKeys: [] },
    { systemVariableKeys: ['sys_user_nickname', 'sys_user_background'] },
  ])(
    'keeps known personal fields friendly when custom metadata overlaps $systemVariableKeys',
    ({ systemVariableKeys }) => {
      const onChange = jest.fn();
      const { container } = render(
        <VariableList
          variables={{
            sys_user_nickname: 'Learner',
            sys_user_background: 'Teacher',
          }}
          systemVariableKeys={systemVariableKeys}
          customVariableKeys={['sys_user_nickname', 'sys_user_background']}
          onChange={onChange}
        />,
      );

      expect(screen.getByText('学生昵称')).toBeInTheDocument();
      expect(screen.getByText('学生背景偏好')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('填写学生昵称')).toHaveValue(
        'Learner',
      );
      expect(screen.getByPlaceholderText('填写学生背景偏好')).toHaveValue(
        'Teacher',
      );
      expect(container.textContent).not.toContain('sys_user_');
      expect(screen.queryByLabelText(/sys_user_/)).not.toBeInTheDocument();

      fireEvent.change(screen.getByRole('textbox', { name: '学生昵称' }), {
        target: { value: 'Updated' },
      });
      expect(onChange).toHaveBeenCalledWith('sys_user_nickname', 'Updated');
    },
  );

  test.each([
    ['hide', '隐藏未使用项'],
    ['restore', '显示全部'],
  ] as const)(
    'shows no tooltips for the %s action or memory rows',
    (actionType, label) => {
      jest.useFakeTimers();
      try {
        const onAction = jest.fn();
        const { container } = render(
          <VariableList
            variables={{ sys_user_nickname: 'Learner' }}
            systemVariableKeys={['sys_user_nickname']}
            actionType={actionType}
            onAction={onAction}
          />,
        );

        const button = screen.getByRole('button', { name: label });
        fireEvent.mouseEnter(button);
        fireEvent.focus(button);
        act(() => jest.advanceTimersByTime(500));

        expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
        expect(container.querySelector('[title]')).toBeNull();
        expect(button).not.toHaveAttribute('aria-describedby');
        fireEvent.click(button);
        expect(onAction).toHaveBeenCalledTimes(1);
      } finally {
        jest.useRealTimers();
      }
    },
  );

  test('renders retired profile keys as ordinary editable course variables', () => {
    const onChange = jest.fn();
    const variables = {
      sex: 'A course answer',
      birth: 'A course date',
      avatar: 'A course character',
      language: 'A programming language',
      sys_user_style: 'A writing exercise',
    };

    render(
      <VariableList
        variables={variables}
        systemVariableKeys={['sys_user_language']}
        customVariableKeys={Object.keys(variables)}
        onChange={onChange}
      />,
    );

    Object.entries(variables).forEach(([key, value]) => {
      expect(screen.getByRole('textbox', { name: key })).toHaveValue(value);
      expect(screen.getByRole('textbox', { name: key })).toHaveAttribute(
        'placeholder',
        '填写模拟回答',
      );
    });
    fireEvent.change(screen.getByDisplayValue('A writing exercise'), {
      target: { value: 'Revised exercise' },
    });
    expect(onChange).toHaveBeenCalledWith('sys_user_style', 'Revised exercise');
  });

  test('updates every visible friendly name when the interface language changes', () => {
    const props = {
      variables: {
        sys_user_nickname: 'Learner',
        sys_user_background: 'Teacher',
        sys_user_input: 'Question',
        sys_user_language: 'Chinese',
      },
      systemVariableKeys: [
        'sys_user_nickname',
        'sys_user_background',
        'sys_user_input',
        'sys_user_language',
      ],
    };
    const { rerender } = render(<VariableList {...props} />);

    expect(screen.getByText('学生昵称')).toBeInTheDocument();
    expect(screen.getByText('学生背景偏好')).toBeInTheDocument();
    expect(screen.getByText('最新输入')).toBeInTheDocument();
    expect(screen.getByText('授课语言')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('填写授课语言')).toBeInTheDocument();

    mockLanguage = 'en-US';
    rerender(<VariableList {...props} />);

    expect(screen.getByText('Student nickname')).toBeInTheDocument();
    expect(
      screen.getByText('Student background and preferences'),
    ).toBeInTheDocument();
    expect(screen.getByText('Latest input')).toBeInTheDocument();
    expect(screen.getByText('Teaching language')).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText('Enter Teaching language'),
    ).toBeInTheDocument();
    expect(screen.queryByText('学生昵称')).not.toBeInTheDocument();
    expect(
      screen.getByRole('textbox', { name: 'Student nickname' }),
    ).toHaveValue('Learner');
    expect(screen.queryByText('sys_user_nickname')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/sys_user_/)).not.toBeInTheDocument();
  });
});
