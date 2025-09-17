import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ExclamationTriangleIcon,
  XCircleIcon,
  LockClosedIcon,
  WifiIcon,
  ShieldExclamationIcon,
} from '@heroicons/react/24/outline';
import { Button } from '@/components/ui/Button';
import { useRouter } from 'next/navigation';
import { useUserStore } from '@/store';
import { PermissionRequestModal } from '@/components/PermissionRequestModal';

interface ErrorDisplayProps {
  errorCode: number;
  errorMessage?: string;
  showDetails?: boolean;
  onRetry?: () => void;
  customAction?: {
    label: string;
    onClick: () => void;
  };
}

// Map error codes to error types for icon selection
const getErrorType = (code: number): string => {
  // Permission errors
  if (code === 401 || code === 9002 || code === 403) {
    return 'permission';
  }
  // Authentication errors
  if (code === 1001 || code === 1004 || code === 1005) {
    return 'auth';
  }
  // Not found errors
  if (code === 404) {
    return 'not-found';
  }
  // Network errors
  if (code >= 500 && code < 600) {
    return 'network';
  }
  // Default
  return 'general';
};

const errorIcons: Record<string, React.ReactNode> = {
  permission: (
    <LockClosedIcon className='w-16 h-16 text-yellow-500 mx-auto mb-4' />
  ),
  auth: (
    <ShieldExclamationIcon className='w-16 h-16 text-red-500 mx-auto mb-4' />
  ),
  network: <WifiIcon className='w-16 h-16 text-red-500 mx-auto mb-4' />,
  'not-found': <XCircleIcon className='w-16 h-16 text-gray-500 mx-auto mb-4' />,
  general: (
    <ExclamationTriangleIcon className='w-16 h-16 text-orange-500 mx-auto mb-4' />
  ),
};

export const ErrorDisplay: React.FC<ErrorDisplayProps> = ({
  errorCode,
  errorMessage,
  showDetails = true,
  onRetry,
  customAction,
}) => {
  const { t } = useTranslation();
  const router = useRouter();
  const isLoggedIn = useUserStore(state => state.isLoggedIn);
  const [showPermissionModal, setShowPermissionModal] = useState(false);

  const handleLogin = () => {
    const currentPath = encodeURIComponent(
      window.location.pathname + window.location.search,
    );
    router.push(`/login?redirect=${currentPath}`);
  };

  const errorType = getErrorType(errorCode);

  // Get title based on error code
  const getTitle = () => {
    switch (errorCode) {
      case 401:
      case 9002:
        return t('c.errors.noPermissionTitle');
      case 403:
        return t('c.errors.forbiddenTitle');
      case 404:
        return t('c.errors.notFoundTitle');
      case 1001:
      case 1004:
      case 1005:
        return t('c.errors.authRequiredTitle');
      default:
        if (errorCode >= 500 && errorCode < 600) {
          return t('c.errors.serverErrorTitle');
        }
        return t('c.errors.generalErrorTitle');
    }
  };

  // Get user-friendly message based on error code
  const getFriendlyMessage = () => {
    switch (errorCode) {
      case 401:
      case 9002:
        return t('c.errors.noPermission');
      case 403:
        return t('c.errors.forbidden');
      case 404:
        return t('c.errors.notFound');
      case 1001:
      case 1004:
      case 1005:
        return t('c.errors.authRequired');
      default:
        if (errorCode >= 500 && errorCode < 600) {
          return t('c.errors.serverError');
        }
        return t('c.errors.generalError');
    }
  };

  // Determine if login button should be shown
  const shouldShowLoginButton = () => {
    return (
      !isLoggedIn &&
      (errorCode === 401 ||
        errorCode === 1001 ||
        errorCode === 1004 ||
        errorCode === 1005)
    );
  };

  // Determine if permission request button should be shown
  const shouldShowPermissionRequest = () => {
    return (
      isLoggedIn &&
      (errorCode === 401 || errorCode === 9002 || errorCode === 403)
    );
  };

  // Handle retry with permission request modal for permission errors
  const handleRetry = () => {
    if (shouldShowPermissionRequest()) {
      setShowPermissionModal(true);
    } else if (onRetry) {
      onRetry();
    }
  };

  return (
    <div className='flex flex-col items-center justify-center h-full min-h-[400px] p-8'>
      <div className='text-center max-w-md'>
        {errorIcons[errorType]}
        <h2 className='text-xl font-semibold text-gray-900 mb-2'>
          {getTitle()}
        </h2>
        <p className='text-gray-600 mb-6'>{getFriendlyMessage()}</p>

        {/* Error details section - Completely hidden in production */}

        <div className='flex gap-3 justify-center mt-8'>
          {shouldShowLoginButton() && (
            <Button
              onClick={handleLogin}
              className='min-w-[120px]'
            >
              {t('c.user.login')}
            </Button>
          )}
          {(onRetry || shouldShowPermissionRequest()) && (
            <Button
              onClick={handleRetry}
              variant='outline'
              className='min-w-[120px]'
            >
              {shouldShowPermissionRequest()
                ? t('c.permission.requestTitle')
                : t('common.retry')}
            </Button>
          )}
          {customAction && (
            <Button
              onClick={customAction.onClick}
              variant={
                onRetry || shouldShowLoginButton() ? 'outline' : 'default'
              }
              className='min-w-[120px]'
            >
              {customAction.label}
            </Button>
          )}
        </div>
      </div>

      <PermissionRequestModal
        open={showPermissionModal}
        onClose={() => setShowPermissionModal(false)}
      />
    </div>
  );
};

export default ErrorDisplay;
