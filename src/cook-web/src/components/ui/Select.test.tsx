import { render } from '@testing-library/react';

import {
  Select,
  SelectContent,
  SelectItem,
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
          <DialogTitle>Select Layering</DialogTitle>
          <DialogDescription>Select layering description</DialogDescription>
          <Select
            open={true}
            value='2101'
            onValueChange={() => undefined}
          >
            <SelectTrigger>
              <SelectValue placeholder='Select grant type' />
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
});

function extractZIndex(layerClass: string): number {
  const match = layerClass.match(/z-\[(\d+)\]/);
  if (!match) {
    throw new Error(`Unexpected z-index layer class: ${layerClass}`);
  }
  return Number(match[1]);
}
