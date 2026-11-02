import React from 'react';
import { render } from '@testing-library/react';
import RuntimeConfigInitializer from './RuntimeConfigInitializer';

let mockFaviconUrl = '';
const mockInitializeEnvData = jest.fn();

jest.mock('@/lib/initialize-runtime-config', () => ({
  initializeEnvData: () => mockInitializeEnvData(),
}));

jest.mock('@/store', () => ({
  useEnvStore: (selector: (state: { faviconUrl: string }) => unknown) =>
    selector({ faviconUrl: mockFaviconUrl }),
}));

describe('runtime site favicon', () => {
  beforeEach(() => {
    mockFaviconUrl = '';
    mockInitializeEnvData.mockReset();
    document.head.innerHTML = '';
  });

  afterEach(() => {
    document.head.innerHTML = '';
  });

  test('restores the platform icons when a custom favicon is cleared', () => {
    const originalHrefs = ['/favicon.ico', '/shortcut.ico', '/apple-icon.png'];
    const links = ['icon', 'shortcut icon', 'apple-touch-icon'].map(
      (rel, index) => {
        const link = document.createElement('link');
        link.rel = rel;
        link.setAttribute('href', originalHrefs[index]);
        document.head.appendChild(link);
        return link;
      },
    );
    mockFaviconUrl = '/customer-favicon.ico';

    const { rerender } = render(<RuntimeConfigInitializer />);

    for (const link of links) {
      expect(link.getAttribute('href')).toMatch(
        /^\/customer-favicon\.ico\?v=\d+$/,
      );
    }

    Object.assign(window.location, { pathname: '/admin' });
    rerender(<RuntimeConfigInitializer />);
    expect(mockInitializeEnvData).toHaveBeenCalledTimes(1);

    mockFaviconUrl = '';
    rerender(<RuntimeConfigInitializer />);

    links.forEach((link, index) => {
      expect(new URL(link.href).pathname).toBe(originalHrefs[index]);
    });
  });

  test('removes an injected customer icon when runtime has no favicon', () => {
    mockFaviconUrl = '/customer-favicon.ico';
    const { rerender } = render(<RuntimeConfigInitializer />);
    expect(document.head.querySelector("link[rel='icon']")).not.toBeNull();

    mockFaviconUrl = '';
    rerender(<RuntimeConfigInitializer />);

    expect(document.head.querySelector("link[rel='icon']")).toBeNull();
  });
});
