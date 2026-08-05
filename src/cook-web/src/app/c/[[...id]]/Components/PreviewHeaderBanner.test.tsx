import React from 'react';
import { render, screen } from '@testing-library/react';
import PreviewHeaderBanner from './PreviewHeaderBanner';

jest.mock('react-i18next', () => {
  const translation =
    '正在预览课程草稿，发布后学生才能看到更新。<editLink>编辑课程</editLink>';

  return {
    Trans: ({ components }: any) => {
      const match = translation.match(/^(.*)<editLink>(.*)<\/editLink>(.*)$/);

      if (!match) {
        return <>{translation}</>;
      }

      return (
        <>
          {match[1]}
          {React.cloneElement(components.editLink, {}, match[2])}
          {match[3]}
        </>
      );
    },
    useTranslation: () => ({
      t: (key: string) => key,
    }),
  };
});

describe('PreviewHeaderBanner', () => {
  it('links the draft notice to the current lesson editor in the same tab', () => {
    render(
      <PreviewHeaderBanner
        courseId='course-1'
        lessonId='lesson-2'
      />,
    );

    expect(
      screen.getByText('正在预览课程草稿，发布后学生才能看到更新。'),
    ).toBeInTheDocument();

    const editLink = screen.getByRole('link', { name: '编辑课程' });
    expect(editLink).toHaveAttribute(
      'href',
      '/shifu/course-1?lessonid=lesson-2',
    );
    expect(editLink).not.toHaveAttribute('target');
  });

  it('omits the lesson query when no current lesson is available', () => {
    render(<PreviewHeaderBanner courseId='course-1' />);

    expect(screen.getByRole('link', { name: '编辑课程' })).toHaveAttribute(
      'href',
      '/shifu/course-1',
    );
  });
});
