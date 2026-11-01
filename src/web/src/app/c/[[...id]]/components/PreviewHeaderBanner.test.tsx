import React from 'react';
import { render, screen } from '@testing-library/react';
import PreviewHeaderBanner from './PreviewHeaderBanner';

jest.mock('react-i18next', () => {
  const draftNotice = 'Draft notice.';

  return {
    Trans: ({ components }: any) => {
      return (
        <>
          {draftNotice}
          {React.cloneElement(components.editLink, {}, 'Edit course')}
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

    expect(screen.getByText('Draft notice.')).toBeInTheDocument();

    const editLinks = screen.getAllByRole('link');
    expect(editLinks).toHaveLength(1);

    const [editLink] = editLinks;
    expect(editLink).toHaveAccessibleName('Edit course');
    expect(editLink).toHaveAttribute(
      'href',
      '/shifu/course-1?lessonid=lesson-2',
    );
    expect(editLink).not.toHaveAttribute('target');
  });

  it('omits the lesson query when no current lesson is available', () => {
    render(<PreviewHeaderBanner courseId='course-1' />);

    expect(screen.getByRole('link', { name: 'Edit course' })).toHaveAttribute(
      'href',
      '/shifu/course-1',
    );
  });
});
