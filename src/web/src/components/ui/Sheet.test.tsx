import { DirectionProvider } from '@radix-ui/react-direction';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from './Sheet';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const TITLE = 'Settings';
const DESCRIPTION = 'Update settings';
const SAVE_LABEL = 'Save';
const CANCEL_LABEL = 'Cancel';

const renderSheet = (
  direction: 'ltr' | 'rtl',
  props: ComponentProps<typeof SheetContent> = {},
) => (
  <DirectionProvider dir={direction}>
    <Sheet open>
      <SheetContent {...props}>
        <SheetHeader data-testid='header'>
          <SheetTitle>{TITLE}</SheetTitle>
          <SheetDescription>{DESCRIPTION}</SheetDescription>
        </SheetHeader>
        <SheetFooter data-testid='footer'>
          <button>{SAVE_LABEL}</button>
          <button>{CANCEL_LABEL}</button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  </DirectionProvider>
);

describe('Sheet direction', () => {
  test.each([
    ['ltr', undefined, 'right', 'l'],
    ['rtl', undefined, 'left', 'r'],
    ['ltr', 'end', 'right', 'l'],
    ['rtl', 'end', 'left', 'r'],
    ['ltr', 'start', 'left', 'r'],
    ['rtl', 'start', 'right', 'l'],
    ['rtl', 'left', 'left', 'r'],
    ['rtl', 'right', 'right', 'l'],
    ['rtl', 'top', 'top', 'b'],
    ['rtl', 'bottom', 'bottom', 't'],
  ] as const)(
    'positions %s %s sheets on the %s with matching animations',
    (direction, side, physicalSide, border) => {
      render(renderSheet(direction, { side }));

      expect(screen.getByRole('dialog')).toHaveAttribute('dir', direction);
      expect(screen.getByRole('dialog')).toHaveClass(
        `${physicalSide}-0`,
        `border-${border}`,
        `data-[state=open]:slide-in-from-${physicalSide}`,
        `data-[state=closed]:slide-out-to-${physicalSide}`,
      );
    },
  );

  test('updates portaled position when direction changes', () => {
    const { rerender } = render(renderSheet('ltr'));
    expect(screen.getByRole('dialog')).toHaveClass('right-0');

    rerender(renderSheet('rtl'));
    expect(screen.getByRole('dialog')).toHaveClass('left-0', 'border-r');
    expect(screen.getByRole('dialog')).not.toHaveClass('right-0', 'border-l');

    rerender(renderSheet('ltr'));
    expect(screen.getByRole('dialog')).toHaveClass('right-0', 'border-l');
    expect(screen.getByRole('dialog')).not.toHaveClass('left-0', 'border-r');
  });

  test('honors explicit direction overrides', () => {
    render(renderSheet('rtl', { dir: 'ltr' }));
    expect(screen.getByRole('dialog')).toHaveAttribute('dir', 'ltr');
    expect(screen.getByRole('dialog')).toHaveClass('right-0');
  });

  test('uses logical close placement, heading alignment and action spacing', () => {
    const onCloseIconClick = jest.fn();
    render(renderSheet('rtl', { onCloseIconClick }));

    const close = screen.getByRole('button', {
      name: 'component.header.close',
    });
    expect(close).toHaveClass('end-4');
    expect(close).not.toHaveClass('right-4');
    expect(screen.getByTestId('header')).toHaveClass('sm:text-start');
    expect(screen.getByTestId('footer')).toHaveClass('sm:gap-2');
    expect(screen.getByTestId('footer')).not.toHaveClass('sm:space-x-2');
    fireEvent.click(close);
    expect(onCloseIconClick).toHaveBeenCalledTimes(1);
  });
});
