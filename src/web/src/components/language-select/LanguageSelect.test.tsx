import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import LanguageSelect from './LanguageSelect';

const mockChangeLanguage = jest.fn<Promise<void>, [string]>(() =>
  Promise.resolve(),
);
const mockTrackEvent = jest.fn(() => Promise.resolve());
const mockSelectValueChange = jest.fn<void, [string]>();

jest.mock('@/i18n', () => ({
  __esModule: true,
  default: { changeLanguage: (value: string) => mockChangeLanguage(value) },
  browserLanguage: 'en-US',
  normalizeLanguage: (value?: string) => value || 'en-US',
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en-US' },
  }),
}));

jest.mock('@/lib/i18n-locales', () => ({
  localeEntries: [
    ['en-US', { label: 'English' }],
    ['es-ES', { label: 'Español (España)' }],
    ['fr-FR', { label: 'Français' }],
  ],
  localeCodes: ['en-US', 'es-ES', 'fr-FR'],
}));

jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('@/components/ui/Select', () => ({
  Select: ({
    children,
    value,
    onValueChange,
  }: {
    children: React.ReactNode;
    value: string;
    onValueChange: (value: string) => void;
  }) => {
    mockSelectValueChange.mockImplementation(onValueChange);
    return (
      <select
        aria-label='Language'
        value={value}
        onChange={event => onValueChange(event.target.value)}
      >
        {children}
      </select>
    );
  },
  SelectContent: ({ children }: { children: React.ReactNode }) => children,
  SelectItem: ({
    children,
    value,
  }: {
    children: React.ReactNode;
    value: string;
  }) => <option value={value}>{children}</option>,
  SelectTrigger: () => null,
  SelectValue: () => null,
}));

describe('LanguageSelect analytics', () => {
  beforeEach(() => {
    mockChangeLanguage.mockClear();
    mockTrackEvent.mockReset().mockResolvedValue(undefined);
    mockSelectValueChange.mockReset();
  });

  it.each(['login', 'learner_menu', 'admin_menu'] as const)(
    'records a Spanish choice on the %s surface with the exact safe payload',
    analyticsSurface => {
      const onSetLanguage = jest.fn();
      render(
        <LanguageSelect
          analyticsSurface={analyticsSurface}
          language='en-US'
          onSetLanguage={onSetLanguage}
        />,
      );

      expect(mockTrackEvent).not.toHaveBeenCalled();
      fireEvent.change(screen.getByRole('combobox', { name: 'Language' }), {
        target: { value: 'es-ES' },
      });

      expect(mockTrackEvent.mock.calls).toEqual([
        [
          'user_language_selected',
          { selected_locale: 'es-ES', surface: analyticsSurface },
        ],
      ]);
      expect(mockTrackEvent.mock.invocationCallOrder[0]).toBeLessThan(
        mockChangeLanguage.mock.invocationCallOrder[0],
      );
      expect(mockChangeLanguage).toHaveBeenCalledWith('es-ES');
      expect(onSetLanguage).toHaveBeenCalledWith('es-ES');
      expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toMatch(
        /Español|https?:|email|token|title|error/,
      );
    },
  );

  it('excludes initialization, prop hydration, same-language and unsupported values', () => {
    const onSetLanguage = jest.fn();
    const { rerender } = render(
      <LanguageSelect
        analyticsSurface='login'
        language='en-US'
        onSetLanguage={onSetLanguage}
      />,
    );
    rerender(
      <LanguageSelect
        analyticsSurface='login'
        language='es-ES'
        onSetLanguage={onSetLanguage}
      />,
    );
    act(() => {
      mockSelectValueChange('es-ES');
      mockSelectValueChange('unsupported-free-text');
    });

    expect(mockTrackEvent).not.toHaveBeenCalled();
    expect(mockChangeLanguage).not.toHaveBeenCalled();
    expect(onSetLanguage).not.toHaveBeenCalled();

    fireEvent.change(screen.getByRole('combobox', { name: 'Language' }), {
      target: { value: 'fr-FR' },
    });
    expect(mockTrackEvent.mock.calls).toEqual([
      [
        'user_language_selected',
        { selected_locale: 'fr-FR', surface: 'login' },
      ],
    ]);
  });

  it('counts a pending target once and allows a retry after the language change fails', async () => {
    let rejectChange!: (reason?: unknown) => void;
    mockChangeLanguage.mockImplementationOnce(
      () =>
        new Promise<void>((_resolve, reject) => {
          rejectChange = reject;
        }),
    );
    const onSetLanguage = jest.fn();
    render(
      <LanguageSelect
        analyticsSurface='login'
        language='en-US'
        onSetLanguage={onSetLanguage}
      />,
    );

    act(() => {
      mockSelectValueChange('es-ES');
      mockSelectValueChange('es-ES');
    });
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    expect(mockChangeLanguage).toHaveBeenCalledTimes(1);

    await act(async () => {
      rejectChange(new Error('language bundle unavailable'));
    });
    act(() => mockSelectValueChange('es-ES'));
    expect(mockTrackEvent).toHaveBeenCalledTimes(2);
    expect(mockChangeLanguage).toHaveBeenCalledTimes(2);
    expect(onSetLanguage).toHaveBeenCalledTimes(2);
  });

  it.each(['throw', 'reject'])(
    'keeps the language action working when tracking will %s',
    async failure => {
      if (failure === 'throw') {
        mockTrackEvent.mockImplementationOnce(() => {
          throw new Error('private analytics failure');
        });
      } else {
        mockTrackEvent.mockRejectedValueOnce(
          new Error('private analytics failure'),
        );
      }
      const onSetLanguage = jest.fn();
      render(
        <LanguageSelect
          analyticsSurface='learner_menu'
          language='en-US'
          onSetLanguage={onSetLanguage}
        />,
      );

      fireEvent.change(screen.getByRole('combobox', { name: 'Language' }), {
        target: { value: 'es-ES' },
      });
      await act(async () => {});

      expect(mockTrackEvent).toHaveBeenCalledTimes(1);
      expect(mockChangeLanguage).toHaveBeenCalledWith('es-ES');
      expect(onSetLanguage).toHaveBeenCalledWith('es-ES');
    },
  );
});
