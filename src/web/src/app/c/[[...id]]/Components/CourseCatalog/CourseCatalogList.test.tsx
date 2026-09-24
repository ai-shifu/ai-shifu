import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CourseCatalogList } from './CourseCatalogList';
import type { LessonTreeCatalog } from '../../hooks/useLessonTree';

jest.mock('@/api/studyV2', () => ({
  LEARNING_PERMISSION: {
    NORMAL: 'normal',
    TRIAL: 'trial',
    GUEST: 'guest',
  },
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'es-ES' },
  }),
}));

jest.mock('@/store', () => ({
  useUserStore: (selector: (state: { isLoggedIn: boolean }) => unknown) =>
    selector({ isLoggedIn: true }),
  useCourseStore: (
    selector: (state: { courseAvatar: string; courseName: string }) => unknown,
  ) => selector({ courseAvatar: '', courseName: '' }),
}));

jest.mock('@/store/useSystemStore', () => ({
  useSystemStore: (selector: (state: { previewMode: boolean }) => unknown) =>
    selector({ previewMode: false }),
}));

jest.mock('@/store/useCourseStore', () => ({
  useCourseStore: (selector: (state: { openPayModal: jest.Mock }) => unknown) =>
    selector({ openPayModal: jest.fn() }),
}));

jest.mock('./ResetChapterButton', () => ({
  __esModule: true,
  default: () => null,
}));

const catalogs: LessonTreeCatalog[] = [
  {
    id: 'chapter-guide',
    name: 'Getting started',
    status: 'learning',
    status_value: 'learning',
    type: 'guest',
    is_paid: true,
    collapse: false,
    lessons: [
      {
        id: 'lesson-guide',
        name: 'How to use this course',
        status: 'learning',
        status_value: 'learning',
        type: 'guest',
        is_paid: true,
        canLearning: true,
        follow_up_mode: 'disabled',
      },
    ],
  },
];

it('uses the guide language for chapter headings, tooltips, and lesson titles', async () => {
  const user = userEvent.setup();
  render(
    <CourseCatalogList
      catalogs={catalogs}
      titleLanguage='en-US'
      hideCourseHeader
    />,
  );

  expect(screen.getByText('How to use this course')).toHaveAttribute(
    'lang',
    'en-US',
  );
  const chapterHeading = screen.getByText('Getting started');
  expect(chapterHeading).toHaveAttribute('lang', 'en-US');

  await user.hover(chapterHeading);
  const tooltip = await screen.findByRole('tooltip');
  expect(tooltip.parentElement).toHaveAttribute('lang', 'en-US');
});

it('lets ordinary Spanish chapter headings inherit the interface language', () => {
  render(
    <CourseCatalogList
      catalogs={[{ ...catalogs[0], name: 'Primeros pasos' }]}
      hideCourseHeader
    />,
  );

  expect(screen.getByText('Primeros pasos')).not.toHaveAttribute('lang');
});

it('passes the guide language to the catalog course heading when shown', () => {
  render(
    <CourseCatalogList
      catalogs={catalogs}
      courseName='AI-Shifu Creation Guide'
      titleLanguage='en-US'
    />,
  );

  expect(screen.getByText('AI-Shifu Creation Guide')).toHaveAttribute(
    'lang',
    'en-US',
  );
});
