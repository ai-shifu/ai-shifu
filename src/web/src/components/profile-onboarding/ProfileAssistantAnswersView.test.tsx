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

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(resolvePromise => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
};

const setup = (initialValue = '') => {
  const onSubmit = jest.fn();
  const onBack = jest.fn();
  const onPromptCopied = jest.fn();
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
        analyticsScope='user-a'
        onPromptCopied={onPromptCopied}
      />
    );
  }
  render(<Harness />);
  return {
    onSubmit,
    onBack,
    onPromptCopied,
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

test('keeps the assistant answer and actions mobile-safe inside its scroller', () => {
  const { input } = setup('Pasted answer');
  const view = screen.getByTestId('profile-assistant-answers');
  const copyButton = screen.getByRole('button', {
    name: 'module.profileOnboarding.assistant.copy',
  });
  const backButton = screen.getByRole('button', {
    name: 'module.profileOnboarding.assistant.back',
  });
  const processButton = screen.getByRole('button', {
    name: 'module.profileOnboarding.assistant.process',
  });

  expect(view).toHaveClass('overflow-y-auto', 'overscroll-contain', 'py-6');
  expect(input).toHaveClass('text-base', 'sm:text-sm');
  expect(copyButton).toHaveClass('min-h-11', 'min-w-20', 'sm:min-h-9');
  expect(backButton).toHaveClass('min-h-11', 'min-w-11', 'sm:min-h-10');
  expect(processButton).toHaveClass('min-h-11', 'min-w-11', 'sm:min-h-10');
});

test('a real stable paste waits for the processing button and submits once', () => {
  const { input, onSubmit } = setup();
  fireEvent.paste(input);
  fireEvent.change(input, { target: { value: 'Pasted answer' } });
  act(() => {
    jest.advanceTimersByTime(600);
  });
  expect(onSubmit).not.toHaveBeenCalled();
  act(() => {
    jest.advanceTimersByTime(5000);
  });
  expect(onSubmit).not.toHaveBeenCalled();
  expect(input).toHaveValue('Pasted answer');
  fireEvent.click(
    screen.getByRole('button', {
      name: 'module.profileOnboarding.assistant.process',
    }),
  );
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

test('returning after paste does not submit the draft', () => {
  const { input, onSubmit, onBack } = setup();
  fireEvent.paste(input);
  fireEvent.change(input, { target: { value: 'Pasted answer' } });
  fireEvent.click(
    screen.getByRole('button', {
      name: 'module.profileOnboarding.assistant.back',
    }),
  );
  act(() => {
    jest.advanceTimersByTime(1000);
  });
  expect(onSubmit).not.toHaveBeenCalled();
  expect(onBack).toHaveBeenCalledTimes(1);
});

test('reenabling processing never submits a pasted draft without a click', () => {
  const onSubmit = jest.fn();
  function Harness({ pending }: { pending: boolean }) {
    const [value, setValue] = React.useState('');
    return (
      <ProfileAssistantAnswersView
        prompt='Public prompt'
        value={value}
        disabled={false}
        processingDisabled={pending}
        unresolved={false}
        onChange={setValue}
        onSubmit={onSubmit}
        onBack={jest.fn()}
      />
    );
  }
  const { rerender } = render(<Harness pending />);
  const input = screen.getByLabelText(
    'module.profileOnboarding.assistant.resultLabel',
  );
  expect(input).toBeEnabled();
  fireEvent.paste(input);
  fireEvent.change(input, {
    target: { value: 'Answer pasted before the question' },
  });
  rerender(<Harness pending={false} />);
  act(() => {
    jest.advanceTimersByTime(1000);
  });
  expect(input).toHaveValue('Answer pasted before the question');
  expect(onSubmit).not.toHaveBeenCalled();
  fireEvent.click(
    screen.getByRole('button', {
      name: 'module.profileOnboarding.assistant.process',
    }),
  );
  expect(onSubmit).toHaveBeenCalledWith('Answer pasted before the question');
});

test('editing after paste submits only the latest draft when processing is clicked', () => {
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
  const { onPromptCopied } = setup();
  const copyButton = screen.getByRole('button', {
    name: 'module.profileOnboarding.assistant.copy',
  });
  expect(screen.getByTestId('profile-assistant-answers')).toHaveClass(
    'flex',
    'h-full',
    'flex-col',
  );
  expect(copyButton).toHaveClass('absolute', 'bottom-2', 'end-2');
  expect(copyButton.parentElement).toHaveClass('relative');
  expect(copyButton.parentElement?.parentElement?.parentElement).toHaveClass(
    'md:flex-1',
    'md:grid-cols-2',
  );
  expect(copyButton).toHaveTextContent(
    'module.profileOnboarding.assistant.copyShort',
  );
  await act(async () => {
    fireEvent.click(copyButton);
  });
  expect(writeText).toHaveBeenCalledWith('Public prompt');
  expect(onPromptCopied).toHaveBeenCalledWith('user-a');
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
  expect(
    screen.getByRole('button', {
      name: 'module.profileOnboarding.assistant.copy',
    }),
  ).toBeEnabled();
  expect(screen.getByText('Public prompt')).toBeVisible();
  expect(onPromptCopied).toHaveBeenCalledTimes(1);
});

test('keeps a delayed successful copy bound to its originating account scope', async () => {
  const clipboardRequest = deferred<void>();
  const writeText = jest.fn().mockReturnValue(clipboardRequest.promise);
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText },
  });
  const onPromptCopied = jest.fn();
  const renderView = (analyticsScope: string) => (
    <ProfileAssistantAnswersView
      prompt='Public prompt'
      value=''
      disabled={false}
      unresolved={false}
      onChange={jest.fn()}
      onSubmit={jest.fn()}
      onBack={jest.fn()}
      analyticsScope={analyticsScope}
      onPromptCopied={onPromptCopied}
    />
  );
  const { rerender } = render(renderView('user-a'));

  fireEvent.click(
    screen.getByRole('button', {
      name: 'module.profileOnboarding.assistant.copy',
    }),
  );
  rerender(renderView('user-b'));
  await act(async () => clipboardRequest.resolve());

  expect(onPromptCopied).toHaveBeenCalledTimes(1);
  expect(onPromptCopied).toHaveBeenCalledWith('user-a');
});

test('counts each concurrent successful clipboard write', async () => {
  const firstCopy = deferred<void>();
  const secondCopy = deferred<void>();
  const writeText = jest
    .fn()
    .mockReturnValueOnce(firstCopy.promise)
    .mockReturnValueOnce(secondCopy.promise);
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText },
  });
  const { onPromptCopied } = setup();
  const copyButton = screen.getByRole('button', {
    name: 'module.profileOnboarding.assistant.copy',
  });

  fireEvent.click(copyButton);
  fireEvent.click(copyButton);
  await act(async () => {
    secondCopy.resolve();
    firstCopy.resolve();
  });

  expect(onPromptCopied).toHaveBeenCalledTimes(2);
  expect(onPromptCopied).toHaveBeenNthCalledWith(1, 'user-a');
  expect(onPromptCopied).toHaveBeenNthCalledWith(2, 'user-a');
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
