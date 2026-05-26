import React from 'react';
import { render, screen } from '@testing-library/react';
import ShifuHistoryPage from './page';

jest.mock('react', () => {
  const actual = jest.requireActual('react');

  return {
    ...actual,
    use: (value: unknown) => value,
  };
});

jest.mock('next/dynamic', () => ({
  __esModule: true,
  default: () =>
    function MockShifuRoot(props: {
      id: string;
      initialLessonId: string | null;
      initialViewMode?: 'edit' | 'history';
    }) {
      return (
        <div data-testid='mock-shifu-root'>
          {`${props.id}:${props.initialLessonId}:${props.initialViewMode}`}
        </div>
      );
    },
}));

jest.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams('lessonid=lesson-42'),
}));

jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock('@/components/MobileUnsupportedDialog', () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock('@/c-utils/urlUtils', () => ({
  __esModule: true,
  getLessonIdFromQuery: jest.fn(() => 'lesson-42'),
}));

describe('ShifuHistoryPage', () => {
  test('passes history view mode into shifu root', () => {
    render(
      <ShifuHistoryPage
        params={{ id: 'shifu-1' } as unknown as Promise<{ id: string }>}
      />,
    );

    expect(screen.getByTestId('mock-shifu-root')).toHaveTextContent(
      'shifu-1:lesson-42:history',
    );
  });
});
