import { render, screen } from '@testing-library/react';
import AgreementPage from './page';
import core from '../../../../i18n/ur-PK/common/core.json';

const mockLegalContent = 'English legal document';
jest.mock('@/components/legals/ZhCnAgreement.mdx', () => () => null);
jest.mock('@/components/legals/ZhCnPrivacy.mdx', () => () => null);
jest.mock('@/components/legals/EnAgreement.mdx', () => () => mockLegalContent);
jest.mock('@/components/legals/EnPrivacy.mdx', () => () => mockLegalContent);
jest.mock('@/i18n', () => ({
  __esModule: true,
  default: { language: 'ur-PK' },
  normalizeLanguage: (language: string) => language,
}));
jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: () => core.legalFallbackEnglishNotice,
  }),
}));

test('labels the English fallback document and keeps its direction independent of Urdu', () => {
  render(<AgreementPage />);
  expect(screen.getByText(core.legalFallbackEnglishNotice)).toBeInTheDocument();
  const documentContent = screen.getByText(mockLegalContent).closest('[lang]');
  expect(documentContent).toHaveAttribute('lang', 'en');
  expect(documentContent).toHaveAttribute('dir', 'ltr');
});
