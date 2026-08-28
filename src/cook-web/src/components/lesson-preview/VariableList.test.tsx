import React from 'react';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fireEvent, render, screen } from '@testing-library/react';
import VariableList from './VariableList';
import styles from './VariableList.module.scss';

const variableListStylesheet = readFileSync(
  join(__dirname, 'VariableList.module.scss'),
  'utf8',
);

const mockTranslations: Record<string, Record<string, string>> = {
  'zh-CN': {
    'module.shifu.previewArea.systemVariableLabels.accessibleName':
      '{label}（{name}）',
    'module.shifu.previewArea.systemVariableLabels.nickname': '学生昵称',
    'module.shifu.previewArea.systemVariableLabels.background': '学生背景偏好',
    'module.shifu.previewArea.systemVariableLabels.input': '最新输入',
    'module.shifu.previewArea.systemVariableLabels.language': '授课语言',
  },
  'en-US': {
    'module.shifu.previewArea.systemVariableLabels.accessibleName':
      '{label} ({name})',
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

  test('crossfades localized names and raw keys within the same name cell', () => {
    const onChange = jest.fn();
    const variables = {
      sys_user_nickname: 'Learner',
      sys_user_background: 'Teacher',
      sys_user_input: 'Question',
      sys_user_language: 'Chinese',
    };

    render(
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
      const friendlyName = screen.getByText(label);
      const rawName = screen.getByText(rawKey);
      const nameCell = friendlyName.closest('button');

      expect(nameCell).not.toBeNull();
      expect(nameCell).toHaveClass(styles.name, styles.systemName);
      expect(nameCell).toContainElement(friendlyName);
      expect(nameCell).toContainElement(rawName);
      expect(friendlyName).toHaveClass(styles.friendlyName);
      expect(rawName).toHaveClass(styles.rawName);
      expect(rawName).toHaveAttribute('dir', 'ltr');
      expect(nameCell).toHaveAttribute('aria-label', `${label}（${rawKey}）`);

      nameCell?.focus();
      expect(nameCell).toHaveFocus();
    });

    fireEvent.change(screen.getByDisplayValue('Learner'), {
      target: { value: 'Alex' },
    });
    expect(onChange).toHaveBeenCalledWith('sys_user_nickname', 'Alex');
  });

  test('keeps the raw layer out of layout and crossfades it on hover or focus', () => {
    expect(variableListStylesheet).toMatch(
      /&:hover \.friendlyName,\s*&:focus-visible \.friendlyName\s*{\s*opacity:\s*0;/,
    );
    expect(variableListStylesheet).toMatch(
      /&:hover \.rawName,\s*&:focus-visible \.rawName\s*{\s*opacity:\s*1;/,
    );
    expect(variableListStylesheet).toMatch(
      /\.rawName\s*{[\s\S]*?position:\s*absolute;[\s\S]*?opacity:\s*0;/,
    );
  });

  test('keeps custom variables raw and falls unknown system variables back to raw', () => {
    render(
      <VariableList
        variables={{
          custom_topic: 'Testing',
          sys_user_future: 'Future',
        }}
        systemVariableKeys={['sys_user_future']}
      />,
    );

    const customNameCell = screen.getByText('custom_topic').closest('div');
    const unknownSystemNameCell = screen
      .getByText('sys_user_future')
      .closest('div');

    expect(customNameCell).toHaveClass(styles.name);
    expect(customNameCell).not.toHaveClass(styles.systemName);
    expect(unknownSystemNameCell).toHaveClass(styles.name);
    expect(unknownSystemNameCell).not.toHaveClass(styles.systemName);
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

    mockLanguage = 'en-US';
    rerender(<VariableList {...props} />);

    expect(screen.getByText('Student nickname')).toBeInTheDocument();
    expect(
      screen.getByText('Student background and preferences'),
    ).toBeInTheDocument();
    expect(screen.getByText('Latest input')).toBeInTheDocument();
    expect(screen.getByText('Teaching language')).toBeInTheDocument();
    expect(screen.queryByText('学生昵称')).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'Student nickname (sys_user_nickname)',
      }),
    ).toBeInTheDocument();
  });
});
