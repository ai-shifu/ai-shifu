import { render, screen } from '@testing-library/react';

import {
  Select,
  SelectContent,
  SELECT_CONTENT_BASE_CLASS,
  SelectItem,
  SELECT_ITEM_BASE_CLASS,
  SelectTrigger,
  SelectValue,
  SELECT_CONTENT_LAYER_CLASS,
} from '@/components/ui/Select';
import { ALERT_DIALOG_CONTENT_LAYER_CLASS } from '@/components/ui/AlertDialog';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DIALOG_CONTENT_LAYER_CLASS,
  DialogTitle,
} from '@/components/ui/Dialog';

const SELECT_ITEM_TEXT = 'Automatic';
const DIALOG_TITLE_TEXT = 'Select Layering';
const DIALOG_DESCRIPTION_TEXT = 'Select layering description';
const SELECT_PLACEHOLDER_TEXT = 'Select grant type';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('Select layering', () => {
  it('keeps select content above dialog and alert dialog layers', () => {
    render(
      <Dialog open={true}>
        <DialogContent>
          <DialogTitle>{DIALOG_TITLE_TEXT}</DialogTitle>
          <DialogDescription>{DIALOG_DESCRIPTION_TEXT}</DialogDescription>
          <Select
            open={true}
            value='2101'
            onValueChange={() => undefined}
          >
            <SelectTrigger>
              <SelectValue placeholder={SELECT_PLACEHOLDER_TEXT} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value='2101'>{SELECT_ITEM_TEXT}</SelectItem>
            </SelectContent>
          </Select>
        </DialogContent>
      </Dialog>,
    );

    const selectContentElement = Array.from(
      document.body.querySelectorAll('*'),
    ).find(element =>
      String(element.className).includes(SELECT_CONTENT_LAYER_CLASS),
    );

    expect(selectContentElement).toBeTruthy();
    expect(selectContentElement?.className).toContain(
      SELECT_CONTENT_LAYER_CLASS,
    );
    expect(extractZIndex(SELECT_CONTENT_LAYER_CLASS)).toBeGreaterThan(
      extractZIndex(DIALOG_CONTENT_LAYER_CLASS),
    );
    expect(extractZIndex(SELECT_CONTENT_LAYER_CLASS)).toBeGreaterThan(
      extractZIndex(ALERT_DIALOG_CONTENT_LAYER_CLASS),
    );
  });

  it('uses the shared content and item spacing classes', () => {
    render(
      <Select
        open={true}
        value='2101'
        onValueChange={() => undefined}
      >
        <SelectTrigger>
          <SelectValue placeholder={SELECT_PLACEHOLDER_TEXT} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value='2101'>{SELECT_ITEM_TEXT}</SelectItem>
        </SelectContent>
      </Select>,
    );

    const selectContentElement = Array.from(
      document.body.querySelectorAll('*'),
    ).find(element =>
      String(element.className).includes(SELECT_CONTENT_LAYER_CLASS),
    );
    const selectItemElement = screen.getByRole('option', {
      name: SELECT_ITEM_TEXT,
    });

    expect(selectContentElement?.className).toContain(
      SELECT_CONTENT_BASE_CLASS.split(' ')[0],
    );
    expect(selectContentElement?.className).toContain('rounded-lg');
    expect(selectItemElement.className).toContain(
      SELECT_ITEM_BASE_CLASS.split(' ')[0],
    );
    expect(selectItemElement.className).toContain('rounded-md');
    expect(selectItemElement.className).toContain('pl-3');
    expect(selectItemElement.className).toContain('pr-9');
  });
});

function extractZIndex(layerClass: string): number {
  const match = layerClass.match(/z-\[(\d+)\]/);
  if (!match) {
    throw new Error(`Unexpected z-index layer class: ${layerClass}`);
  }
  return Number(match[1]);
}
