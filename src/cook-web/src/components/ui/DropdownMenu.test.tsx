import { render, screen } from '@testing-library/react';

import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DROPDOWN_MENU_CHECKABLE_ITEM_BASE_CLASS,
  DROPDOWN_MENU_CONTENT_BASE_CLASS,
  DROPDOWN_MENU_CONTENT_LAYER_CLASS,
  DropdownMenuItem,
  DROPDOWN_MENU_ITEM_BASE_CLASS,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/DropdownMenu';

const DROPDOWN_TRIGGER_TEXT = 'More';
const DROPDOWN_ITEM_TEXT = 'Open details';
const DROPDOWN_CHECKBOX_ITEM_TEXT = 'Pin row';
const DROPDOWN_RADIO_ITEM_TEXT = 'Newest first';

describe('DropdownMenu styling', () => {
  it('keeps dropdown content above dialog layers and uses shared item spacing', () => {
    render(
      <DropdownMenu open={true}>
        <DropdownMenuTrigger asChild>
          <button type='button'>{DROPDOWN_TRIGGER_TEXT}</button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem>{DROPDOWN_ITEM_TEXT}</DropdownMenuItem>
          <DropdownMenuCheckboxItem checked={true}>
            {DROPDOWN_CHECKBOX_ITEM_TEXT}
          </DropdownMenuCheckboxItem>
          <DropdownMenuRadioItem value='newest'>
            {DROPDOWN_RADIO_ITEM_TEXT}
          </DropdownMenuRadioItem>
        </DropdownMenuContent>
      </DropdownMenu>,
    );

    const dropdownContentElement = Array.from(
      document.body.querySelectorAll('*'),
    ).find(element =>
      String(element.className).includes(DROPDOWN_MENU_CONTENT_LAYER_CLASS),
    );
    const dropdownItemElement = screen.getByRole('menuitem', {
      name: DROPDOWN_ITEM_TEXT,
    });
    const dropdownCheckboxItemElement = screen.getByRole('menuitemcheckbox', {
      name: DROPDOWN_CHECKBOX_ITEM_TEXT,
    });
    const dropdownRadioItemElement = screen.getByRole('menuitemradio', {
      name: DROPDOWN_RADIO_ITEM_TEXT,
    });

    expect(dropdownContentElement).toBeTruthy();
    expect(dropdownContentElement?.className).toContain(
      DROPDOWN_MENU_CONTENT_BASE_CLASS.split(' ')[0],
    );
    expect(dropdownContentElement?.className).toContain('rounded-lg');
    expect(dropdownItemElement.className).toContain(
      DROPDOWN_MENU_ITEM_BASE_CLASS.split(' ')[0],
    );
    expect(dropdownItemElement.className).toContain('rounded-md');
    expect(dropdownItemElement.className).toContain('px-3');
    expect(dropdownCheckboxItemElement.className).toContain(
      DROPDOWN_MENU_CHECKABLE_ITEM_BASE_CLASS.split(' ')[0],
    );
    expect(dropdownCheckboxItemElement.className).toContain('pr-9');
    expect(dropdownRadioItemElement.className).toContain(
      DROPDOWN_MENU_CHECKABLE_ITEM_BASE_CLASS.split(' ')[0],
    );
    expect(dropdownRadioItemElement.className).toContain('pr-9');
  });
});
