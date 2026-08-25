jest.unmock('i18next');

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import i18next from 'i18next';
import { I18nextProvider } from 'react-i18next';

import I18nDocumentAttributes from './I18nDocumentAttributes';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/DropdownMenu';
import { Select, SelectTrigger, SelectValue } from '@/components/ui/Select';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/Tabs';

// Avoid application bootstrap side effects; these tests use canonical locales.
jest.mock('@/i18n', () => ({
  normalizeLanguage: (language: string) => language,
}));

// Mirror Next's build-time injection while exercising the real metadata reader.
jest.mock('@/lib/i18n-locales', () => {
  process.env.NEXT_PUBLIC_I18N_META = JSON.stringify(
    jest.requireActual('../../../i18n/locales.json'),
  );
  return jest.requireActual('@/lib/i18n-locales');
});

const LANGUAGE_LABEL = 'Language';
const MENU_LABEL = 'Actions';
const MENU_ITEM_LABEL = 'Details';
const TAB_LABELS = ['First', 'Second', 'Third'];

describe('I18nDocumentAttributes direction context', () => {
  afterEach(() => {
    document.documentElement.lang = 'en-US';
    document.documentElement.dir = 'ltr';
  });

  test.each([
    ['ar-SA', 'rtl'],
    ['en-US', 'ltr'],
    ['fr-FR', 'ltr'],
    ['th-TH', 'ltr'],
    ['zh-CN', 'ltr'],
  ])(
    'propagates %s direction to Select and portaled Menu',
    async (language, direction) => {
      const i18n = i18next.createInstance();
      await i18n.init({ lng: language, resources: {}, fallbackLng: false });

      render(
        <I18nextProvider i18n={i18n}>
          <I18nDocumentAttributes>
            <Select>
              <SelectTrigger aria-label={LANGUAGE_LABEL}>
                <SelectValue />
              </SelectTrigger>
            </Select>
            <DropdownMenu
              open
              modal={false}
            >
              <DropdownMenuTrigger>{MENU_LABEL}</DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuItem>{MENU_ITEM_LABEL}</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </I18nDocumentAttributes>
        </I18nextProvider>,
      );

      expect(document.documentElement).toHaveAttribute('lang', language);
      expect(document.documentElement).toHaveAttribute('dir', direction);
      expect(screen.getByRole('combobox')).toHaveAttribute('dir', direction);
      expect(screen.getByRole('menu')).toHaveAttribute('dir', direction);
    },
  );

  test('updates direction and keyboard navigation when the language changes', async () => {
    const i18n = i18next.createInstance();
    await i18n.init({ lng: 'en-US', resources: {}, fallbackLng: false });

    render(
      <I18nextProvider i18n={i18n}>
        <I18nDocumentAttributes>
          <Tabs defaultValue='First'>
            <TabsList>
              {TAB_LABELS.map(label => (
                <TabsTrigger
                  key={label}
                  value={label}
                >
                  {label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </I18nDocumentAttributes>
      </I18nextProvider>,
    );

    await act(async () => {
      await i18n.changeLanguage('ar-SA');
    });
    const first = screen.getByRole('tab', { name: 'First' });
    const second = screen.getByRole('tab', { name: 'Second' });
    act(() => first.focus());
    fireEvent.keyDown(first, { key: 'ArrowLeft' });
    await waitFor(() => expect(second).toHaveFocus());
    expect(document.documentElement).toHaveAttribute('dir', 'rtl');

    await act(async () => {
      await i18n.changeLanguage('th-TH');
    });
    fireEvent.keyDown(second, { key: 'ArrowRight' });
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Third' })).toHaveFocus();
    });
    expect(document.documentElement).toHaveAttribute('lang', 'th-TH');
    expect(document.documentElement).toHaveAttribute('dir', 'ltr');
  });
});
