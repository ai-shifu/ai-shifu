import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';

import { useEnvStore } from '@/c-store/envStore';
import ChatLayout from './layout';

let mockPathname = '/c/course-1';
const childLabel = 'content';

jest.mock('next/navigation', () => ({
  usePathname: () => mockPathname,
}));

const originalLocation = window.location;

describe('course route entry redirect', () => {
  beforeEach(() => {
    mockPathname = '/c/course-1';
  });

  afterEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    });
    act(() => {
      useEnvStore.setState({
        courseId: '',
        homeUrl: '',
        runtimeConfigLoaded: false,
      });
    });
  });

  it('rechecks HOME_URL after client navigation to bare /c despite a stale course id', async () => {
    const replace = jest.fn();
    const location = {
      href: 'https://app.example.com/c/course-1',
      pathname: '/c/course-1',
      replace,
    };
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: location,
    });
    act(() => {
      useEnvStore.setState({
        courseId: 'stale-course',
        homeUrl: '/c/default-course',
        runtimeConfigLoaded: true,
      });
    });

    const { rerender } = render(
      <ChatLayout>
        <div>{childLabel}</div>
      </ChatLayout>,
    );

    await act(async () => {});
    expect(replace).not.toHaveBeenCalled();
    expect(screen.getByText(childLabel)).toBeInTheDocument();

    mockPathname = '/c';
    location.href = 'https://app.example.com/c';
    location.pathname = '/c';
    rerender(
      <ChatLayout>
        <div>{childLabel}</div>
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith('/c/default-course');
    });
    expect(screen.queryByText(childLabel)).not.toBeInTheDocument();
  });

  it('waits for the runtime HOME_URL before redirecting a direct /c entry', async () => {
    const replace = jest.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        href: 'https://app.example.com/c',
        pathname: '/c',
        replace,
      },
    });
    mockPathname = '/c';

    render(
      <ChatLayout>
        <div>{childLabel}</div>
      </ChatLayout>,
    );

    await act(async () => {});
    expect(replace).not.toHaveBeenCalled();
    expect(screen.queryByText(childLabel)).not.toBeInTheDocument();

    act(() => {
      useEnvStore.setState({
        homeUrl: '/c/runtime-course',
        runtimeConfigLoaded: true,
      });
    });

    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith('/c/runtime-course');
    });
  });
});
