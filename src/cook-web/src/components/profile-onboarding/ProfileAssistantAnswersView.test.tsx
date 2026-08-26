import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { ProfileAssistantAnswersView } from './ProfileAssistantAnswersView';
import {
  readProfileAssistantDraft,
  writeProfileAssistantDraft,
  clearProfileAssistantDrafts,
} from '@/lib/profileAssistantDraft';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const setup = (initialValue = '') => {
  const onSubmit = jest.fn();
  const onBack = jest.fn();
  function Harness() {
    const [value, setValue] = React.useState(initialValue);
    return (
      <ProfileAssistantAnswersView
        prompt='Public prompt'
        value={value}
        disabled={false}
        unresolved={false}
        onChange={setValue}
        onSubmit={onSubmit}
        onBack={onBack}
      />
    );
  }
  render(<Harness />);
  return {
    onSubmit,
    onBack,
    input: screen.getByLabelText(
      'module.profileOnboarding.assistant.resultLabel',
    ),
  };
};

beforeEach(() => {
  jest.useFakeTimers();
  window.sessionStorage.clear();
});
afterEach(() => {
  jest.useRealTimers();
});

test('only a real stable paste submits once after 600ms', () => {
  const { input, onSubmit } = setup();
  fireEvent.paste(input);
  fireEvent.change(input, { target: { value: 'Pasted answer' } });
  act(() => {
    jest.advanceTimersByTime(599);
  });
  expect(onSubmit).not.toHaveBeenCalled();
  act(() => {
    jest.advanceTimersByTime(1);
  });
  expect(onSubmit).toHaveBeenCalledTimes(1);
  expect(onSubmit).toHaveBeenCalledWith('Pasted answer');
});

test('typing, draft restoration, composition and over-limit paste never auto-submit', () => {
  const { input, onSubmit } = setup('Restored answer');
  act(() => {
    jest.advanceTimersByTime(1000);
  });
  fireEvent.change(input, { target: { value: 'Typed answer' } });
  act(() => {
    jest.advanceTimersByTime(1000);
  });
  fireEvent.compositionStart(input);
  fireEvent.paste(input);
  fireEvent.change(input, { target: { value: 'Composed answer' } });
  fireEvent.compositionEnd(input);
  act(() => {
    jest.advanceTimersByTime(1000);
  });
  fireEvent.paste(input);
  fireEvent.change(input, { target: { value: '🧠'.repeat(10_001) } });
  act(() => {
    jest.advanceTimersByTime(1000);
  });
  expect(onSubmit).not.toHaveBeenCalled();
  expect(
    screen.getByRole('button', {
      name: 'module.profileOnboarding.assistant.process',
    }),
  ).toBeDisabled();
});

test('an empty or cancelled paste does not arm the next ordinary keystroke', () => {
  const { input, onSubmit } = setup();
  fireEvent.paste(input);
  act(() => {
    jest.advanceTimersByTime(0);
  });
  fireEvent.change(input, { target: { value: 'Typed later' } });
  act(() => {
    jest.advanceTimersByTime(1000);
  });
  expect(onSubmit).not.toHaveBeenCalled();
});

test('an edit after paste cancels auto-submit and manual processing remains available', () => {
  const { input, onSubmit } = setup();
  fireEvent.paste(input);
  fireEvent.change(input, { target: { value: 'Pasted' } });
  fireEvent.change(input, { target: { value: 'Edited' } });
  act(() => {
    jest.advanceTimersByTime(1000);
  });
  expect(onSubmit).not.toHaveBeenCalled();
  fireEvent.click(
    screen.getByRole('button', {
      name: 'module.profileOnboarding.assistant.process',
    }),
  );
  expect(onSubmit).toHaveBeenCalledWith('Edited');
});

test('copy uses the exact frozen prompt and offers manual copying on clipboard failure', async () => {
  const writeText = jest.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText },
  });
  setup();
  await act(async () => {
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.assistant.copy',
      }),
    );
  });
  expect(writeText).toHaveBeenCalledWith('Public prompt');
  expect(
    screen.getByRole('button', {
      name: 'module.profileOnboarding.assistant.copied',
    }),
  ).toBeInTheDocument();
  writeText.mockRejectedValue(new Error('Unavailable'));
  await act(async () => {
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.profileOnboarding.assistant.copied',
      }),
    );
  });
  expect(screen.getByRole('alert')).toHaveTextContent(
    'module.profileOnboarding.assistant.copyFailed',
  );
  expect(screen.getByText('Public prompt')).toBeVisible();
});

test('restores only the same account draft and clears legacy, previous-account and logout data', () => {
  window.sessionStorage.setItem(
    'profile-onboarding-paste-draft:profile-v2',
    'Unscoped legacy',
  );
  expect(readProfileAssistantDraft('user-a')).toBe('');
  writeProfileAssistantDraft('user-a', 'Private A');
  expect(readProfileAssistantDraft('user-a')).toBe('Private A');
  expect(readProfileAssistantDraft('user-b')).toBe('');
  expect(
    window.sessionStorage.getItem(
      'profile-onboarding-paste-draft:profile-v2:user-a',
    ),
  ).toBeNull();
  writeProfileAssistantDraft('user-b', 'Private B');
  clearProfileAssistantDrafts();
  expect(readProfileAssistantDraft('user-b')).toBe('');
  expect(
    window.sessionStorage.getItem('profile-onboarding-paste-draft:profile-v2'),
  ).toBeNull();
});

test('storage failures do not prevent continuing the flow', () => {
  const getItem = jest
    .spyOn(Storage.prototype, 'getItem')
    .mockImplementation(() => {
      throw new Error('Blocked');
    });
  expect(readProfileAssistantDraft('account')).toBe('');
  expect(() => clearProfileAssistantDrafts()).not.toThrow();
  getItem.mockRestore();
  const setItem = jest
    .spyOn(Storage.prototype, 'setItem')
    .mockImplementation(() => {
      throw new Error('Full');
    });
  expect(() => writeProfileAssistantDraft('account', 'answer')).not.toThrow();
  setItem.mockRestore();
});

test.each([undefined, 'missing-account-key', 'unrelated-session-key'])(
  'clears all account drafts with an absent or stale active pointer (%s)',
  activeKey => {
    const storage = window.sessionStorage;
    storage.setItem('unrelated-session-key', 'Keep this value');
    storage.setItem(
      'profile-onboarding-paste-draft:profile-v2',
      'Legacy draft',
    );
    writeProfileAssistantDraft('account-a', 'Private A');
    writeProfileAssistantDraft('account-b', 'Private B');
    if (activeKey) {
      storage.setItem(
        'profile-onboarding-paste-draft:active-user:profile-v2',
        activeKey,
      );
    }

    clearProfileAssistantDrafts();

    expect(storage.length).toBe(1);
    expect(storage.getItem('unrelated-session-key')).toBe('Keep this value');
  },
);

test.each(['key', 'removeItem'] as const)(
  'tolerates storage %s failures while clearing drafts',
  method => {
    writeProfileAssistantDraft('account', 'Private answer');
    const failingMethod = jest
      .spyOn(Storage.prototype, method)
      .mockImplementation(() => {
        throw new Error('Storage blocked');
      });
    try {
      expect(() => clearProfileAssistantDrafts()).not.toThrow();
    } finally {
      failingMethod.mockRestore();
    }
  },
);
