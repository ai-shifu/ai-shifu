import { render, screen } from '@testing-library/react';

import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from '@/components/ui/AlertDialog';

const ALERT_DIALOG_TITLE = 'Confirm import';
const ALERT_DIALOG_DESCRIPTION = 'Confirmation dialog description';
const ALERT_DIALOG_CONTENT = 'Alert content';

describe('AlertDialog layering', () => {
  it('keeps confirmation dialogs above base dialog layers', () => {
    render(
      <AlertDialog open={true}>
        <AlertDialogContent>
          <AlertDialogTitle>{ALERT_DIALOG_TITLE}</AlertDialogTitle>
          <AlertDialogDescription>
            {ALERT_DIALOG_DESCRIPTION}
          </AlertDialogDescription>
          <div>{ALERT_DIALOG_CONTENT}</div>
        </AlertDialogContent>
      </AlertDialog>,
    );

    const openElements = Array.from(
      document.body.querySelectorAll('[data-state="open"]'),
    );
    const overlayElement = openElements.find(element =>
      element.className.includes('z-[110]'),
    );

    expect(overlayElement).toBeTruthy();
    expect(screen.getByRole('alertdialog')).toHaveClass('z-[111]');
  });
});
