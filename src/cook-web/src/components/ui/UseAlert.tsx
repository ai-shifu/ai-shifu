'use client';
import React from 'react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/AlertDialog';

interface AlertOptions {
  title: string;
  description: React.ReactNode;
  descriptionAsChild?: boolean;
  confirmText?: string;
  cancelText?: string;
  showConfirm?: boolean;
  onConfirm?: () => void;
  onCancel?: () => void;
}

interface AlertContextType {
  open: boolean;
  options: AlertOptions;
  showAlert: (options: AlertOptions) => void;
  hideAlert: () => void;
}

const AlertContext = React.createContext<AlertContextType | undefined>(
  undefined,
);

export function AlertProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const [options, setOptions] = React.useState<AlertOptions>({
    title: '',
    description: '',
    confirmText: 'Ok',
    cancelText: 'Cancel',
  });

  const showAlert = React.useCallback((options: AlertOptions) => {
    setOptions(options);
    setOpen(true);
  }, []);

  const hideAlert = React.useCallback(() => {
    setOpen(false);
  }, []);

  const handleConfirm = () => {
    options.onConfirm?.();
    hideAlert();
  };

  const handleCancel = () => {
    options.onCancel?.();
    hideAlert();
  };

  return (
    <AlertContext.Provider value={{ open, options, showAlert, hideAlert }}>
      {children}
      <AlertDialog
        open={open}
        onOpenChange={setOpen}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{options.title}</AlertDialogTitle>
            {options.descriptionAsChild &&
            React.isValidElement(options.description) ? (
              <AlertDialogDescription asChild>
                {options.description}
              </AlertDialogDescription>
            ) : (
              <AlertDialogDescription>
                {options.description}
              </AlertDialogDescription>
            )}
          </AlertDialogHeader>
          <AlertDialogFooter>
            {options.showConfirm === false ? (
              <AlertDialogAction
                className='h-8'
                onClick={handleConfirm}
              >
                {options.confirmText || options.cancelText || 'Close'}
              </AlertDialogAction>
            ) : (
              <>
                <AlertDialogCancel
                  className='h-8'
                  onClick={handleCancel}
                >
                  {options.cancelText || 'Cancel'}
                </AlertDialogCancel>
                <AlertDialogAction
                  className='h-8'
                  onClick={handleConfirm}
                >
                  {options.confirmText || 'Confirm'}
                </AlertDialogAction>
              </>
            )}
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </AlertContext.Provider>
  );
}

export function useAlert() {
  const context = React.useContext(AlertContext);
  if (!context) {
    throw new Error('useAlert must be used within an AlertProvider');
  }
  return context;
}
