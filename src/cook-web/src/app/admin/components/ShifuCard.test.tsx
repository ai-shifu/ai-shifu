import React from 'react';
import { render, screen } from '@testing-library/react';

import ShifuCard from './ShifuCard';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('ShifuCard', () => {
  test('keeps the course actions trigger visible without hover', () => {
    render(
      <ShifuCard
        id='course-1'
        image={undefined}
        title='Course 1'
        description='Course description'
        isFavorite={false}
        onImportActivationRequest={jest.fn()}
      />,
    );

    const actionsTrigger = screen.getByRole('button', {
      name: 'common.core.more',
    });

    expect(actionsTrigger).not.toHaveClass('opacity-0');
    expect(actionsTrigger).toHaveClass('h-8', 'w-8', 'bg-transparent');
    expect(actionsTrigger.closest('a')).toBeNull();
  });

  test('marks the course cover image as decorative', () => {
    const { container } = render(
      <ShifuCard
        id='course-1'
        image='https://example.com/cover.png'
        title='Course 1'
        description='Course description'
        isFavorite={false}
      />,
    );

    expect(screen.queryByRole('img')).toBeNull();

    const cover = container.querySelector(
      'img[src="https://example.com/cover.png"]',
    );
    expect(cover).not.toBeNull();
    expect(cover).toHaveAttribute('alt', '');
    expect(cover).toHaveAttribute('aria-hidden', 'true');
  });
});
