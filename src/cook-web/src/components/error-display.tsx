import React from 'react';
import { useTranslation } from 'react-i18next';
import { 
  ExclamationTriangleIcon, 
  XCircleIcon,
  LockClosedIcon,
  WifiIcon,
  ShieldExclamationIcon
} from '@heroicons/react/24/outline';
import { Button } from '@/components/ui/button';
import { useRouter } from 'next/navigation';
import { useUserStore } from '@/c-store/useUserStore';

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
  permission: <LockClosedIcon className="w-16 h-16 text-yellow-500 mx-auto mb-4" />,
  auth: <ShieldExclamationIcon className="w-16 h-16 text-red-500 mx-auto mb-4" />,
  network: <WifiIcon className="w-16 h-16 text-red-500 mx-auto mb-4" />,
  'not-found': <XCircleIcon className="w-16 h-16 text-gray-500 mx-auto mb-4" />,
  general: <ExclamationTriangleIcon className="w-16 h-16 text-orange-500 mx-auto mb-4" />
};

export const ErrorDisplay: React.FC<ErrorDisplayProps> = ({ 
  errorCode,
  errorMessage, 
  showDetails = true,
  onRetry,
  customAction
}) => {
  const { t } = useTranslation();
  const router = useRouter();
  const isLoggedIn = useUserStore(state => state.isLoggedIn);
  
  const handleLogin = () => {
    const currentPath = encodeURIComponent(window.location.pathname + window.location.search);
    router.push(`/login?redirect=${currentPath}`);
  };

  const errorType = getErrorType(errorCode);
  
  // Get title based on error code
  const getTitle = () => {
    switch (errorCode) {
      case 401:
      case 9002:
        return t('c.errors.no-permission-title');
      case 403:
        return t('c.errors.forbidden-title');
      case 404:
        return t('c.errors.not-found-title');
      case 1001:
      case 1004:
      case 1005:
        return t('c.errors.auth-required-title');
      default:
        if (errorCode >= 500 && errorCode < 600) {
          return t('c.errors.server-error-title');
        }
        return t('c.errors.general-error-title');
    }
  };

  // Get user-friendly message based on error code
  const getFriendlyMessage = () => {
    switch (errorCode) {
      case 401:
      case 9002:
        return t('c.errors.no-permission');
      case 403:
        return t('c.errors.forbidden');
      case 404:
        return t('c.errors.not-found');
      case 1001:
      case 1004:
      case 1005:
        return t('c.errors.auth-required');
      default:
        if (errorCode >= 500 && errorCode < 600) {
          return t('c.errors.server-error');
        }
        return t('c.errors.general-error');
    }
  };

  // Determine if login button should be shown
  const shouldShowLoginButton = () => {
    return !isLoggedIn && (
      errorCode === 401 || 
      errorCode === 1001 || 
      errorCode === 1004 || 
      errorCode === 1005
    );
  };

  return (
    <div className="flex flex-col items-center justify-center h-full min-h-[400px] p-8">
      <div className="text-center max-w-md">
        {errorIcons[errorType]}
        <h2 className="text-xl font-semibold text-gray-900 mb-2">
          {getTitle()}
        </h2>
        <p className="text-gray-600 mb-2">
          {getFriendlyMessage()}
        </p>
        
        {/* Error details section */}
        {showDetails && (
          <div className="mt-4 p-3 bg-gray-100 rounded-md text-left">
            <p className="text-sm text-gray-700 font-mono">
              <span className="font-semibold">{t('c.errors.error-code')}:</span> {errorCode}
            </p>
            {errorMessage && (
              <p className="text-sm text-gray-700 font-mono mt-1">
                <span className="font-semibold">{t('c.errors.error-message')}:</span> {errorMessage}
              </p>
            )}
          </div>
        )}
        
        <div className="flex gap-3 justify-center mt-6">
          {shouldShowLoginButton() && (
            <Button 
              onClick={handleLogin}
              className="min-w-[120px]"
            >
              {t('c.user.login')}
            </Button>
          )}
          {onRetry && (
            <Button 
              onClick={onRetry}
              variant="outline"
              className="min-w-[120px]"
            >
              {t('common.retry')}
            </Button>
          )}
          {customAction && (
            <Button 
              onClick={customAction.onClick}
              variant={onRetry || shouldShowLoginButton() ? 'outline' : 'default'}
              className="min-w-[120px]"
            >
              {customAction.label}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};

export default ErrorDisplay;