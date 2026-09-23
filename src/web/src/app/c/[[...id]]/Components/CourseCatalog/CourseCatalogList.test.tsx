import { render, screen } from '@testing-library/react';
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

it('passes the guide course language through the catalog to its lesson titles', () => {
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
});
