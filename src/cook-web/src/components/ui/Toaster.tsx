'use client';

import * as React from 'react';
import { usePathname } from 'next/navigation';

import { useToast } from '@/hooks/useToast';
import {
  Toast,
  ToastClose,
  ToastDescription,
  ToastProvider,
  ToastTitle,
  ToastViewport,
} from '@/components/ui/Toast';

export function Toaster() {
  const pathname = usePathname();
  const previousPathnameRef = React.useRef(pathname);
  const { toasts, dismiss } = useToast();

  React.useEffect(() => {
    if (previousPathnameRef.current === pathname) {
      return;
    }

    previousPathnameRef.current = pathname;
    toasts.forEach(currentToast => {
      if (currentToast.dismissOnNavigation) {
        dismiss(currentToast.id);
      }
    });
  }, [dismiss, pathname, toasts]);

  return (
    <ToastProvider>
      {toasts.map(function ({
        id,
        title,
        description,
        action,
        dismissOnNavigation,
        ...props
      }) {
        void dismissOnNavigation;
        return (
          <Toast
            key={id}
            {...props}
          >
            <div className='grid gap-1'>
              {title && <ToastTitle>{title}</ToastTitle>}
              {description && (
                <ToastDescription>{description}</ToastDescription>
              )}
            </div>
            {action}
            <ToastClose />
          </Toast>
        );
      })}
      <ToastViewport />
    </ToastProvider>
  );
}
