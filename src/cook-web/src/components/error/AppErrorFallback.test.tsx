import { render, screen, waitFor } from '@testing-library/react';

import AppErrorFallback from './AppErrorFallback';

const originalLocation = window.location;
const chunkReloadStorageKey = 'ai-shifu:chunk-load-auto-reload-at';

const mockLocationReload = () => {
  const reload = jest.fn();
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: {
      href: 'https://dev.ai-shifu.com/admin/billing?tab=packages',
      reload,
    },
  });
  return reload;
};

describe('AppErrorFallback chunk load recovery', () => {
  afterEach(() => {
    window.sessionStorage.clear();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    });
    jest.restoreAllMocks();
  });

  it('automatically reloads once when a deployed chunk cannot be loaded', async () => {
    const reload = mockLocationReload();
    const error = new Error(
      'Loading chunk 5365 failed. (error: https://dev.ai-shifu.com/_next/static/chunks/5365.js)',
    );
    error.name = 'ChunkLoadError';

    render(<AppErrorFallback error={error} />);

    await waitFor(() => {
      expect(reload).toHaveBeenCalledTimes(1);
    });
    expect(
      screen.getByText('页面资源已更新，正在自动刷新...'),
    ).toBeInTheDocument();
  });

  it('shows the fallback instead of reloading repeatedly for the same chunk error', async () => {
    const reload = mockLocationReload();
    window.sessionStorage.setItem(chunkReloadStorageKey, String(Date.now()));
    const error = new Error('Loading chunk 5365 failed.');
    error.name = 'ChunkLoadError';

    render(<AppErrorFallback error={error} />);

    await waitFor(() => {
      expect(screen.getByText('应用程序发生错误')).toBeInTheDocument();
    });
    expect(reload).not.toHaveBeenCalled();
  });

  it('clears the chunk reload marker for unrelated errors', async () => {
    mockLocationReload();
    window.sessionStorage.setItem(chunkReloadStorageKey, String(Date.now()));

    render(<AppErrorFallback error={new Error('Unexpected runtime error')} />);

    await waitFor(() => {
      expect(window.sessionStorage.getItem(chunkReloadStorageKey)).toBeNull();
    });
  });
});
