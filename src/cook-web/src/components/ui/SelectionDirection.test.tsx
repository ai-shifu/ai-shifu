import { DirectionProvider } from '@radix-ui/react-direction';
import { render, screen } from '@testing-library/react';

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from './Select';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuShortcut,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from './DropdownMenu';

const LABEL = 'Language';
const OPTION = 'Arabic';
const SUBMENU = 'More actions';
const SHORTCUT = 'Ctrl+K';

describe.each(['ltr', 'rtl'] as const)('%s selection visuals', direction => {
  test('aligns Select text and reserves the logical end for the check', () => {
    render(
      <DirectionProvider dir={direction}>
        <Select
          open
          value='ar-SA'
        >
          <SelectTrigger data-testid='trigger'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectLabel data-testid='label'>{LABEL}</SelectLabel>
              <SelectItem value='ar-SA'>{OPTION}</SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
      </DirectionProvider>,
    );

    expect(screen.getByTestId('trigger')).toHaveClass('text-start');
    expect(screen.getByTestId('trigger')).not.toHaveClass('text-left');
    expect(screen.getByRole('listbox')).toHaveAttribute('dir', direction);
    expect(screen.getByTestId('label')).toHaveClass('ps-8', 'pe-2');
    const option = screen.getByRole('option', { name: OPTION });
    expect(option).toHaveClass('ps-3', 'pe-9');
    expect(option).not.toHaveClass('pl-3', 'pr-9');
    expect(option.querySelector('.absolute')).toHaveClass('end-2');
  });

  test('mirrors checkable items, insets, shortcuts, and submenu affordances', () => {
    render(
      <DirectionProvider dir={direction}>
        <DropdownMenu
          open
          modal={false}
        >
          <DropdownMenuTrigger>{LABEL}</DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuLabel
              inset
              data-testid='label'
            >
              {LABEL}
            </DropdownMenuLabel>
            <DropdownMenuCheckboxItem checked>
              {OPTION}
            </DropdownMenuCheckboxItem>
            <DropdownMenuRadioGroup value='ar-SA'>
              <DropdownMenuRadioItem value='ar-SA'>
                {OPTION}
              </DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
            <DropdownMenuItem
              inset
              data-testid='item'
            >
              {OPTION}
              <DropdownMenuShortcut data-testid='shortcut'>
                {SHORTCUT}
              </DropdownMenuShortcut>
            </DropdownMenuItem>
            <DropdownMenuSub>
              <DropdownMenuSubTrigger inset>{SUBMENU}</DropdownMenuSubTrigger>
            </DropdownMenuSub>
          </DropdownMenuContent>
        </DropdownMenu>
        ,
      </DirectionProvider>,
    );

    expect(screen.getByRole('menu')).toHaveAttribute('dir', direction);
    for (const role of ['menuitemcheckbox', 'menuitemradio']) {
      const item = screen.getByRole(role, { name: OPTION });
      expect(item).toHaveAttribute('aria-checked', 'true');
      expect(item).toHaveClass('ps-3', 'pe-9');
      expect(item).not.toHaveClass('pl-3', 'pr-9');
      expect(item.querySelector('.absolute')).toHaveClass('end-2');
    }
    expect(screen.getByTestId('label')).toHaveClass('ps-8');
    expect(screen.getByTestId('item')).toHaveClass('ps-8');
    expect(screen.getByTestId('shortcut')).toHaveClass('ms-auto');
    const submenu = screen.getByRole('menuitem', { name: SUBMENU });
    expect(submenu).toHaveClass('ps-8');
    expect(submenu.querySelector('svg')).toHaveClass(
      'ms-auto',
      'rtl:rotate-180',
    );
  });
});
