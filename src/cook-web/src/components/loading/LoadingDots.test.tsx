import { render, screen } from '@testing-library/react';

import { LoadingDots } from '@/components/loading';

describe('LoadingDots', () => {
  it('renders four dots by default', () => {
    render(<LoadingDots ariaLabel='Loading dots' />);

    const loading = screen.getByLabelText('Loading dots');

    expect(loading.children).toHaveLength(4);
  });

  it('supports custom sizing, spacing, and dot count', () => {
    render(
      <LoadingDots
        ariaLabel='Custom loading dots'
        count={5}
        durationMs={1000}
        gap={8}
        size={14}
      />,
    );

    const loading = screen.getByLabelText('Custom loading dots');
    const dots = Array.from(loading.children) as HTMLElement[];

    expect(dots).toHaveLength(5);
    expect(loading).toHaveStyle({ gap: '8px' });
    expect(dots[0]).toHaveStyle({
      width: '14px',
      height: '14px',
      animationDelay: '0ms',
    });
    expect(dots[4]).toHaveStyle({ animationDelay: '800ms' });
  });
});
