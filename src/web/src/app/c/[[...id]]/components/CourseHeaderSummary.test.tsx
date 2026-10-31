import { render, screen } from '@testing-library/react';
import { CourseHeaderSummary } from './CourseHeaderSummary';

jest.mock('@/store', () => ({
  useCourseStore: (
    selector: (state: { courseAvatar: string; courseName: string }) => unknown,
  ) => selector({ courseAvatar: '', courseName: '' }),
}));

it('uses the authored guide language for its course heading', () => {
  render(
    <CourseHeaderSummary
      courseName='AI-Shifu Creation Guide'
      titleLanguage='en-US'
    />,
  );

  expect(screen.getByText('AI-Shifu Creation Guide')).toHaveAttribute(
    'lang',
    'en-US',
  );
});

it('lets ordinary course headings inherit the interface language', () => {
  render(<CourseHeaderSummary courseName='Curso de IA' />);

  expect(screen.getByText('Curso de IA')).not.toHaveAttribute('lang');
});
