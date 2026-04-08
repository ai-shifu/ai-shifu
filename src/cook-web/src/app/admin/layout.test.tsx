import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { buildAdminMenuItems } from './admin-menu';
import AdminLayout, { SidebarContent } from './layout';

const footerLabel = 'footer';

jest.mock('next/image', () => ({
  __esModule: true,
  default: ({ alt, src }: { alt: string; src: string }) =>
    React.createElement('img', { alt, src }),
}));

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({
    children,
    href,
    ...props
  }: {
    children: React.ReactNode;
    href: string;
  }) => (
    <a
      href={href}
      {...props}
    >
      {children}
    </a>
  ),
}));

jest.mock('next/navigation', () => ({
  usePathname: () => '/admin',
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: 'zh-CN',
    },
  }),
}));

jest.mock('@/c-common/hooks/useDisclosure', () => ({
  useDisclosure: () => ({
    open: false,
    onToggle: jest.fn(),
    onClose: jest.fn(),
  }),
}));

jest.mock('@/config/environment', () => ({
  environment: {
    logoWideUrl: '/logo.png',
  },
}));

jest.mock('@/c-store', () => ({
  __esModule: true,
  useEnvStore: () => '/logo.png',
}));

const mockUserStoreState = {
  isInitialized: true,
  isGuest: false,
  userInfo: {
    is_operator: false,
  },
};

jest.mock('@/store', () => ({
  __esModule: true,
  useUserStore: (selector: (state: typeof mockUserStoreState) => unknown) =>
    selector(mockUserStoreState),
}));

jest.mock('@/app/c/[[...id]]/Components/NavDrawer/NavFooter', () => ({
  __esModule: true,
  default: React.forwardRef(function MockNavFooter(
    {
      onClick,
    }: {
      onClick?: () => void;
    },
    ref,
  ) {
    void ref;
    return <button onClick={onClick}>{footerLabel}</button>;
  }),
}));

jest.mock('@/app/c/[[...id]]/Components/NavDrawer/MainMenuModal', () => ({
  __esModule: true,
  default: () => null,
}));

describe('SidebarContent', () => {
  const t = (key: string) => key;
  const findOperationsCourseLink = () =>
    screen.queryByRole('link', { name: 'common.core.courseManagement' });
  const baseProps = {
    footerRef: { current: null },
    userMenuOpen: false,
    onFooterClick: jest.fn(),
    onUserMenuClose: jest.fn(),
    userMenuClassName: 'user-menu',
    logoSrc: '/logo.png',
  };

  beforeEach(() => {
    baseProps.onFooterClick.mockReset();
    baseProps.onUserMenuClose.mockReset();
  });

  test('auto expands the operations menu when the course submenu is active', () => {
    render(
      <SidebarContent
        {...baseProps}
        menuItems={buildAdminMenuItems({ t, isOperator: true })}
        activePath='/admin/operations'
      />,
    );

    const operationsButton = screen.getByRole('button', {
      name: 'common.core.operations',
    });
    const courseLink = findOperationsCourseLink();

    expect(operationsButton).toHaveAttribute('aria-expanded', 'true');
    expect(operationsButton.className).not.toContain('text-gray-900');
    expect(courseLink).toBeDefined();
    expect(courseLink).toHaveAttribute('href', '/admin/operations');
    expect(courseLink).toHaveAttribute('aria-current', 'page');
  });

  test('toggles the operations submenu open and closed', () => {
    render(
      <SidebarContent
        {...baseProps}
        menuItems={buildAdminMenuItems({ t, isOperator: true })}
        activePath='/admin'
      />,
    );

    const operationsButton = screen.getByRole('button', {
      name: 'common.core.operations',
    });

    expect(operationsButton).toHaveAttribute('aria-expanded', 'false');
    expect(findOperationsCourseLink()).toBeNull();

    fireEvent.click(operationsButton);

    expect(operationsButton).toHaveAttribute('aria-expanded', 'true');
    expect(findOperationsCourseLink()).toHaveAttribute(
      'href',
      '/admin/operations',
    );

    fireEvent.click(operationsButton);

    expect(operationsButton).toHaveAttribute('aria-expanded', 'false');
    expect(findOperationsCourseLink()).toBeNull();
  });
});

describe('AdminLayout', () => {
  const childText = 'content';

  beforeEach(() => {
    mockUserStoreState.isInitialized = true;
    mockUserStoreState.isGuest = false;
    mockUserStoreState.userInfo = {
      is_operator: false,
    };
  });

  test('shows sidebar loading placeholder before user state is ready', () => {
    mockUserStoreState.isInitialized = false;
    mockUserStoreState.userInfo = null as unknown as {
      is_operator: false;
    };

    render(
      <AdminLayout>
        <div>{childText}</div>
      </AdminLayout>,
    );

    expect(screen.getByLabelText('admin-sidebar-loading')).toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'common.core.shifu' }),
    ).not.toBeInTheDocument();
  });

  test('keeps sidebar in loading state for guests before redirect completes', () => {
    mockUserStoreState.isInitialized = true;
    mockUserStoreState.isGuest = true;
    mockUserStoreState.userInfo = null as unknown as {
      is_operator: false;
    };

    render(
      <AdminLayout>
        <div>{childText}</div>
      </AdminLayout>,
    );

    expect(screen.getByLabelText('admin-sidebar-loading')).toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'common.core.shifu' }),
    ).not.toBeInTheDocument();
  });

  test('renders sidebar once initialization completes even if user info is unavailable', () => {
    mockUserStoreState.isInitialized = true;
    mockUserStoreState.isGuest = false;
    mockUserStoreState.userInfo = null as unknown as {
      is_operator: false;
    };

    render(
      <AdminLayout>
        <div>{childText}</div>
      </AdminLayout>,
    );

    expect(
      screen.queryByLabelText('admin-sidebar-loading'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'common.core.shifu' }),
    ).toBeInTheDocument();
  });
});
