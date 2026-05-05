import { render, screen } from '@testing-library/react';

import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
  ALERT_DIALOG_CONTENT_LAYER_CLASS,
  ALERT_DIALOG_OVERLAY_LAYER_CLASS,
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
      element.className.includes(ALERT_DIALOG_OVERLAY_LAYER_CLASS),
    );

    expect(overlayElement).toBeTruthy();
    expect(screen.getByRole('alertdialog')).toHaveClass(
      ALERT_DIALOG_CONTENT_LAYER_CLASS,
    );
  });

  it('keeps the internal content layer when callers pass a lower z-index', () => {
    render(
      <AlertDialog open={true}>
        <AlertDialogContent className='z-[51]'>
          <AlertDialogTitle>{ALERT_DIALOG_TITLE}</AlertDialogTitle>
          <AlertDialogDescription>
            {ALERT_DIALOG_DESCRIPTION}
          </AlertDialogDescription>
          <div>{ALERT_DIALOG_CONTENT}</div>
        </AlertDialogContent>
      </AlertDialog>,
    );

    const dialog = screen.getByRole('alertdialog');

    expect(dialog).toHaveClass(ALERT_DIALOG_CONTENT_LAYER_CLASS);
    expect(dialog).not.toHaveClass('z-[51]');
  });
});
