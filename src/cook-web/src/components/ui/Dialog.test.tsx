import { render, screen, waitFor } from '@testing-library/react';
import { act } from 'react';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/Dialog';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

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
});
