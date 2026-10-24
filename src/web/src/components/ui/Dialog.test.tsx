import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { act } from 'react';

import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('Dialog dismissal', () => {
  it.each(['none', 'onPointerDownOutside', 'onInteractOutside'] as const)(
    'allows explicit outside dismissal while honoring the %s guard',
    async guard => {
      const onOpenChange = jest.fn();
      let pending = true;
      const onOutside = jest.fn((event: Event) => {
        if (pending) event.preventDefault();
      });

      render(
        <Dialog
          defaultOpen
          onOpenChange={onOpenChange}
        >
          <DialogContent
            closeOnOutsideClick
            {...(guard === 'none' ? {} : { [guard]: onOutside })}
          >
            <DialogTitle>Dialog</DialogTitle>
            <DialogDescription>Dialog description</DialogDescription>
          </DialogContent>
        </Dialog>,
      );

      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 0));
      });
      fireEvent.pointerDown(document.body, { pointerType: 'mouse' });
      fireEvent.click(document.body);

      if (guard !== 'none') {
        expect(onOutside).toHaveBeenCalledTimes(1);
        expect(onOpenChange).not.toHaveBeenCalled();
        expect(screen.getByRole('dialog')).toBeInTheDocument();

        pending = false;
        fireEvent.pointerDown(document.body, { pointerType: 'mouse' });
        fireEvent.click(document.body);
      }

      expect(onOpenChange).toHaveBeenCalledWith(false);
      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      });
    },
  );

  it('keeps the dialog open on outside clicks while preserving outside callbacks', async () => {
    const onOpenChange = jest.fn();
    const onPointerDownOutside = jest.fn();
    const onInteractOutside = jest.fn();

    render(
      <Dialog
        defaultOpen
        onOpenChange={onOpenChange}
      >
        <DialogContent
          onPointerDownOutside={onPointerDownOutside}
          onInteractOutside={onInteractOutside}
        >
          <DialogTitle>Dialog</DialogTitle>
          <DialogDescription>Dialog description</DialogDescription>
        </DialogContent>
      </Dialog>,
    );

    // Radix registers its outside pointer listener on the next task.
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    fireEvent.pointerDown(document.body, { pointerType: 'mouse' });
    fireEvent.click(document.body);

    expect(onPointerDownOutside).toHaveBeenCalledTimes(1);
    expect(onInteractOutside).toHaveBeenCalledTimes(1);
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it.each(['escape', 'close icon', 'cancel button'])(
    'still closes through the %s',
    async method => {
      const onOpenChange = jest.fn();

      render(
        <Dialog
          defaultOpen
          onOpenChange={onOpenChange}
        >
          <DialogContent>
            <DialogTitle>Dialog</DialogTitle>
            <DialogDescription>Dialog description</DialogDescription>
            <DialogClose>Cancel</DialogClose>
          </DialogContent>
        </Dialog>,
      );

      if (method === 'escape') {
        fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
      } else {
        fireEvent.click(
          screen.getByRole('button', {
            name: method === 'close icon' ? 'component.header.close' : 'Cancel',
          }),
        );
      }

      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      });
      expect(onOpenChange).toHaveBeenCalledWith(false);
    },
  );
});

describe('Dialog fullscreen portal', () => {
  let fullscreenElement: Element | null = null;

  beforeEach(() => {
    fullscreenElement = null;

    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      get: () => fullscreenElement,
    });
  });

  afterEach(() => {
    fullscreenElement = null;

    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      get: () => null,
    });
  });

  it('renders dialog content inside the active fullscreen element', () => {
    const fullscreenRoot = document.createElement('div');
    fullscreenRoot.setAttribute('data-testid', 'fullscreen-root');
    document.body.appendChild(fullscreenRoot);
    fullscreenElement = fullscreenRoot;

    render(
      <Dialog open={true}>
        <DialogContent>
          <DialogTitle>Fullscreen Dialog</DialogTitle>
          <DialogDescription>Fullscreen dialog description</DialogDescription>
          <div>Portal content</div>
        </DialogContent>
      </Dialog>,
    );

    expect(screen.getByText('Portal content')).toBeInTheDocument();
    expect(fullscreenRoot).toContainElement(screen.getByText('Portal content'));
  });

  it('updates the portal container after entering fullscreen', async () => {
    const fullscreenRoot = document.createElement('div');
    document.body.appendChild(fullscreenRoot);

    render(
      <Dialog open={true}>
        <DialogContent>
          <DialogTitle>Fullscreen Dialog</DialogTitle>
          <DialogDescription>Fullscreen dialog description</DialogDescription>
          <div>Portal content</div>
        </DialogContent>
      </Dialog>,
    );

    act(() => {
      fullscreenElement = fullscreenRoot;
      document.dispatchEvent(new Event('fullscreenchange'));
    });

    await waitFor(() => {
      expect(fullscreenRoot).toContainElement(
        screen.getByText('Portal content'),
      );
    });
  });

  it('keeps the base dialog layers above slide loading overlays', () => {
    render(
      <Dialog open={true}>
        <DialogContent>
          <DialogTitle>Layered Dialog</DialogTitle>
          <DialogDescription>Layered dialog description</DialogDescription>
          <div>Dialog content</div>
        </DialogContent>
      </Dialog>,
    );

    const openElements = Array.from(
      document.body.querySelectorAll('[data-state="open"]'),
    );
    const overlayElement = openElements.find(element =>
      element.className.includes('z-[100]'),
    );

    expect(overlayElement).toBeTruthy();
    expect(screen.getByRole('dialog')).toHaveClass('z-[101]');
  });

  it('allows one dialog to use a lighter contextual overlay', () => {
    render(
      <Dialog open={true}>
        <DialogContent overlayClassName='bg-slate-950/45'>
          <DialogTitle>Contextual Dialog</DialogTitle>
          <DialogDescription>Context remains visible</DialogDescription>
        </DialogContent>
      </Dialog>,
    );

    const overlayElement = Array.from(
      document.body.querySelectorAll('[data-state="open"]'),
    ).find(element => element.className.includes('z-[100]'));

    expect(overlayElement).toHaveClass('bg-slate-950/45');
  });

  it('uses logical alignment and spacing that mirror in RTL layouts', () => {
    render(
      <Dialog open={true}>
        <DialogContent>
          <DialogHeader data-testid='dialog-header'>
            <DialogTitle>RTL Dialog</DialogTitle>
            <DialogDescription>RTL dialog description</DialogDescription>
          </DialogHeader>
          <DialogFooter data-testid='dialog-footer'>Actions</DialogFooter>
        </DialogContent>
      </Dialog>,
    );

    expect(screen.getByTestId('dialog-header')).toHaveClass('sm:text-start');
    expect(screen.getByTestId('dialog-footer')).toHaveClass('sm:gap-2');
    expect(
      screen.getByRole('button', { name: 'component.header.close' }),
    ).toHaveClass('end-4');
  });
});
