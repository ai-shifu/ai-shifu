'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { StarIcon } from '@heroicons/react/24/solid';
import { MoreHorizontal } from 'lucide-react';
import api from '@/api';
import { Shifu } from '@/types/shifu';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { Button } from '@/components/ui/Button';
import { Card, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from '@/components/ui/DropdownMenu';
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
import { CreateShifuDialog } from '@/components/create-shifu-dialog';
import { useToast } from '@/hooks/useToast';
import { useRouter } from 'next/navigation';
import Loading from '@/components/loading';
import { useTranslation } from 'react-i18next';
import { ErrorWithCode } from '@/lib/request';
import ErrorDisplay from '@/components/ErrorDisplay';
import MobileUnsupportedDialog from '@/components/MobileUnsupportedDialog';
import ShifuPermissionDialog from '@/components/shifu-setting/ShifuPermissionDialog';
import { useUserStore } from '@/store';
import { useTracking } from '@/c-common/hooks/useTracking';
import { getCourseCreatorUrl } from '@/c-utils/urlUtils';
import { useCreatorOnboardingStatus } from '@/hooks/useOnboarding';
import { canManageArchive as canManageArchiveForShifu } from '@/lib/shifu-permissions';
import {
  buildGuideCourseTargetId,
  buildOnboardingTargetProps,
  ONBOARDING_TARGET_IDS,
} from '@/lib/onboardingTargets';
import AdminBreadcrumb from './components/AdminBreadcrumb';
import AdminTitle from './components/AdminTitle';

interface ShifuCardProps {
  id: string;
  image: string | undefined;
  title: string;
  description: string;
  isFavorite: boolean;
  archived?: boolean;
  canManageArchive?: boolean;
  canManagePermissions?: boolean;
  onArchiveRequest?: () => void;
  onPermissionRequest?: () => void;
  onboardingTargetId?: string;
}

const CARD_CONTAINER_CLASS =
  'w-full h-full min-h-[118px] rounded-[var(--border-radius-rounded-xl,14px)] border border-[var(--base-border,#E5E5E5)] bg-[var(--base-card,#FFF)] transition-colors duration-200 ease-in-out hover:bg-primary/[0.04]';
const CARD_CONTAINER_STYLE: React.CSSProperties = {
  boxShadow:
    'var(--shadow-sm-1-offset-x, 0) var(--shadow-sm-1-offset-y, 1px) var(--shadow-sm-1-blur-radius, 3px) var(--shadow-sm-1-spread-radius, 0) var(--shadow-sm-1-color, rgba(0, 0, 0, 0.10)), var(--shadow-sm-2-offset-x, 0) var(--shadow-sm-2-offset-y, 1px) var(--shadow-sm-2-blur-radius, 2px) var(--shadow-sm-2-spread-radius, -1px) var(--shadow-sm-2-color, rgba(0, 0, 0, 0.10))',
};
const CARD_CONTENT_CLASS = 'p-4 flex flex-col h-full cursor-pointer';
const COURSE_AVATAR_CLASS =
  'mr-3 flex h-7 w-7 shrink-0 items-center justify-center rounded-[8px]';
const COURSE_AVATAR_EMPTY_STYLE: React.CSSProperties = {
  backgroundColor: '#CFCED4',
};
const COURSE_TABS_LIST_CLASS =
  'h-auto rounded-[var(--border-radius-rounded-lg,10px)] bg-[var(--base-muted,#F5F5F5)] p-[3px]';
const COURSE_TABS_TRIGGER_CLASS =
  'min-w-[100px] gap-[var(--spacing-2,8px)] rounded-[var(--border-radius-rounded-md,8px)] border-[length:var(--border-width-border,1px)] border-transparent px-[var(--spacing-2,8px)] py-[var(--spacing-1,4px)] text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)] data-[state=active]:border-[var(--custom-dark-input,rgba(255,255,255,0.00))] data-[state=active]:bg-[var(--custom-background-dark-input-30,#FFF)] data-[state=active]:shadow-[var(--shadow-sm-1-offset-x,0)_var(--shadow-sm-1-offset-y,1px)_var(--shadow-sm-1-blur-radius,3px)_var(--shadow-sm-1-spread-radius,0)_var(--shadow-sm-1-color,rgba(0,0,0,0.10)),var(--shadow-sm-2-offset-x,0)_var(--shadow-sm-2-offset-y,1px)_var(--shadow-sm-2-blur-radius,2px)_var(--shadow-sm-2-spread-radius,-1px)_var(--shadow-sm-2-color,rgba(0,0,0,0.10))]';

const ShifuCard = ({
  id,
  image,
  title,
  description,
  isFavorite,
  archived,
  canManageArchive,
  canManagePermissions,
  onArchiveRequest,
  onPermissionRequest,
  onboardingTargetId,
}: ShifuCardProps) => {
  const { t } = useTranslation();
  const showMenu = Boolean(canManageArchive || canManagePermissions);

  return (
    <div
      className='relative w-full h-full group'
      {...(onboardingTargetId
        ? buildOnboardingTargetProps(onboardingTargetId)
        : {})}
    >
      <Link
        href={`/shifu/${id}`}
        target='_blank'
        rel='noopener noreferrer'
        className='block w-full h-full'
      >
        <Card
          className={CARD_CONTAINER_CLASS}
          style={CARD_CONTAINER_STYLE}
        >
          <CardContent className={CARD_CONTENT_CLASS}>
            <div className='mb-4 flex flex-row items-center justify-between'>
              <div className='flex min-w-0 flex-row items-center w-full'>
                <div
                  className={COURSE_AVATAR_CLASS}
                  style={!image ? COURSE_AVATAR_EMPTY_STYLE : undefined}
                >
                  {image && (
                    <img
                      src={image}
                      alt='recipe'
                      className='h-full w-full rounded-[8px] object-cover'
                    />
                  )}
                  {!image && (
                    <img
                      src='/icons/logo.svg'
                      alt=''
                      aria-hidden='true'
                      className='h-[19px] w-4 object-contain'
                    />
                  )}
                </div>

                <h3 className='overflow-hidden text-ellipsis whitespace-nowrap text-[16px] font-medium leading-5 text-black'>
                  {title}
                </h3>
                {archived && (
                  <Badge className='ml-2 rounded-full bg-muted text-muted-foreground px-2 py-0 text-xs whitespace-nowrap'>
                    {t('common.core.archived')}
                  </Badge>
                )}
              </div>
              <div className='flex items-center gap-2'>
                {isFavorite && <StarIcon className='w-5 h-5 text-yellow-400' />}
              </div>
            </div>
            <p className='min-h-[1.25rem] break-words break-all text-sm font-normal leading-5 text-[color:rgba(10,10,10,0.65)] line-clamp-3'>
              {description || ''}
            </p>
          </CardContent>
        </Card>
      </Link>
      {showMenu && (
        <DropdownMenu>
          {/* Reveal the menu when hovering the whole card, while keeping click behavior unchanged. */}
          <div className='absolute top-0 right-0 h-10 w-10 flex items-center justify-center z-10 group'>
            <DropdownMenuTrigger asChild>
              <Button
                type='button'
                variant='ghost'
                size='icon'
                className='h-8 w-8 opacity-0 transition-opacity group-hover:opacity-100 data-[state=open]:opacity-100'
                title={t('common.core.more')}
                aria-label={t('common.core.more')}
                onClick={event => {
                  event.preventDefault();
                  event.stopPropagation();
                }}
              >
                <MoreHorizontal className='h-4 w-4 text-muted-foreground' />
              </Button>
            </DropdownMenuTrigger>
          </div>
          <DropdownMenuContent
            align='end'
            sideOffset={0}
            className='min-w-0'
          >
            {canManageArchive && (
              <DropdownMenuItem
                onSelect={event => {
                  event.stopPropagation();
                  onArchiveRequest?.();
                }}
              >
                {archived
                  ? t('module.shifuSetting.unarchive')
                  : t('module.shifuSetting.archive')}
              </DropdownMenuItem>
            )}
            {canManagePermissions && (
              <DropdownMenuItem
                onSelect={event => {
                  event.stopPropagation();
                  onPermissionRequest?.();
                }}
              >
                {t('module.shifuSetting.permissionManage')}
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  );
};

const ScriptManagementPage = () => {
  const router = useRouter();
  const { toast } = useToast();
  const { trackEvent } = useTracking();
  const { t, i18n } = useTranslation();
  const isInitialized = useUserStore(state => state.isInitialized);
  const isGuest = useUserStore(state => state.isGuest);
  const isLoggedIn = useUserStore(state => state.isLoggedIn);
  const currentUserId = useUserStore(state => state.userInfo?.user_id || '');
  const hasAuthenticatedAdminSession = isInitialized && isLoggedIn && !isGuest;
  const hasResolvedAdminSession =
    hasAuthenticatedAdminSession && Boolean(currentUserId);
  const { data: onboardingStatus } = useCreatorOnboardingStatus(
    hasResolvedAdminSession,
  );
  const [courseCreatorUrl, setCourseCreatorUrl] = useState<string | null>(null);
  const [adminReady, setAdminReady] = useState(false);
  const [permissionRetryNonce, setPermissionRetryNonce] = useState(0);
  const [activeTab, setActiveTab] = useState<'all' | 'archived'>('all');
  const [shifus, setShifus] = useState<Shifu[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [showCreateShifuModal, setShowCreateShifuModal] = useState(false);
  const [error, setError] = useState<{ message: string; code?: number } | null>(
    null,
  );
  const [archiveDialogOpen, setArchiveDialogOpen] = useState(false);
  const [archiveLoading, setArchiveLoading] = useState(false);
  const [archiveTarget, setArchiveTarget] = useState<Shifu | null>(null);
  const [permissionDialogOpen, setPermissionDialogOpen] = useState(false);
  const [permissionTarget, setPermissionTarget] = useState<Shifu | null>(null);
  const pageSize = 30;
  const currentPage = useRef(1);
  const containerRef = useRef(null);
  const fetchShifusRef = useRef<(() => Promise<void>) | null>(null);
  const loadingRef = useRef(false);
  const hasMoreRef = useRef(true);
  const listVersionRef = useRef(0);

  const activeTabRef = useRef<'all' | 'archived'>(activeTab);
  const guideCourseTargetId = buildGuideCourseTargetId(
    onboardingStatus?.guide_course.bid,
  );

  useEffect(() => {
    activeTabRef.current = activeTab;
  }, [activeTab]);

  useEffect(() => {
    setCourseCreatorUrl(getCourseCreatorUrl());
  }, []);

  const setHasMoreState = useCallback((value: boolean) => {
    hasMoreRef.current = value;
    setHasMore(value);
  }, []);

  const fetchShifus = useCallback(async () => {
    if (loadingRef.current || !hasMoreRef.current) return;

    const requestVersion = listVersionRef.current;
    loadingRef.current = true;
    setLoading(true);
    try {
      // Use a snapshot of the tab at request time to avoid mixing responses
      // when users switch tabs before the API returns.
      const requestTab = activeTabRef.current;
      const isArchivedTab = requestTab === 'archived';
      const { items } = await api.getShifuList({
        page_index: currentPage.current,
        page_size: pageSize,
        archived: isArchivedTab,
      });
      if (requestVersion !== listVersionRef.current) {
        return;
      }

      if (process.env.NODE_ENV !== 'production') {
        console.info('[shifu-list] request page', currentPage.current);
        console.info('[shifu-list] fetched items', items.length);
        console.info('[shifu-list] hasMore before', hasMoreRef.current);
      }

      if (requestTab !== activeTabRef.current) {
        return;
      }
      if (items.length < pageSize) {
        setHasMoreState(false);
      }

      setShifus(prev => {
        // Prevent duplicate records
        const existingIds = new Set(prev.map(shifu => shifu.bid));
        const newItems = items.filter(
          (item: Shifu) => !existingIds.has(item.bid),
        );
        if (process.env.NODE_ENV !== 'production') {
          console.info('[shifu-list] existing ids count', existingIds.size);
          console.info('[shifu-list] new items count', newItems.length);
        }
        return [...prev, ...newItems];
      });
      currentPage.current += 1;
      if (process.env.NODE_ENV !== 'production') {
        console.info('[shifu-list] next page', currentPage.current);
        console.info('[shifu-list] hasMore after', hasMoreRef.current);
      }
    } catch (error: any) {
      if (requestVersion !== listVersionRef.current) {
        return;
      }
      console.error('Failed to fetch shifus:', error);
      if (error instanceof ErrorWithCode) {
        // Pass the error code and original message to ErrorDisplay
        // ErrorDisplay will handle the translation based on error code
        setError({ message: error.message, code: error.code });
      } else {
        // For unknown errors, pass a generic error code
        setError({ message: error.message || 'Unknown error', code: 0 });
      }
    } finally {
      if (requestVersion === listVersionRef.current) {
        loadingRef.current = false;
        setLoading(false);
      }
    }
  }, [pageSize, setHasMoreState]);

  // Store the latest fetchShifus in ref
  fetchShifusRef.current = fetchShifus;
  const onCreateShifu = async (values: any) => {
    try {
      const response = await api.createShifu(values);
      toast({
        title: t('common.core.createSuccess'),
        description: t('common.core.createSuccessDescription'),
      });
      setShowCreateShifuModal(false);
      trackEvent('creator_shifu_create_success', {
        shifu_bid: response.bid,
        shifu_name: response.name,
      });
      // Redirect to edit page instead of refreshing list
      router.push(`/shifu/${response.bid}`);
    } catch (error) {
      toast({
        title: t('common.core.createFailed'),
        description:
          error instanceof Error
            ? error.message
            : t('common.core.unknownError'),
        variant: 'destructive',
      });
    }
  };

  const handleCreateShifuModal = () => {
    trackEvent('creator_shifu_create_click', {});
    setShowCreateShifuModal(true);
  };

  const resetListAndFetch = useCallback(() => {
    listVersionRef.current += 1;
    setShifus([]);
    setHasMoreState(true);
    loadingRef.current = false;
    setLoading(false);
    currentPage.current = 1;
    setError(null);
    if (fetchShifusRef.current) {
      fetchShifusRef.current();
    }
  }, [setHasMoreState]);

  const canManageArchive = useCallback(
    (shifu: Shifu) => canManageArchiveForShifu(shifu, currentUserId),
    [currentUserId],
  );

  const canManagePermissions = useCallback(
    (shifu: Shifu) => {
      if (typeof shifu.can_manage_permissions === 'boolean') {
        return shifu.can_manage_permissions;
      }
      return (
        Boolean(shifu.created_user_bid) &&
        shifu.created_user_bid === currentUserId
      );
    },
    [currentUserId],
  );

  const handleArchiveRequest = useCallback((shifu: Shifu) => {
    setArchiveTarget(shifu);
    setArchiveDialogOpen(true);
  }, []);

  const handlePermissionRequest = useCallback((shifu: Shifu) => {
    setPermissionTarget(shifu);
    setPermissionDialogOpen(true);
  }, []);

  const handleArchiveConfirm = useCallback(async () => {
    if (!archiveTarget?.bid || archiveLoading) {
      return;
    }
    if (!canManageArchive(archiveTarget)) {
      return;
    }
    setArchiveLoading(true);
    try {
      if (archiveTarget.archived) {
        await api.unarchiveShifu({ shifu_bid: archiveTarget.bid });
        toast({
          title: t('module.shifuSetting.unarchiveSuccess'),
        });
      } else {
        await api.archiveShifu({ shifu_bid: archiveTarget.bid });
        toast({
          title: t('module.shifuSetting.archiveSuccess'),
        });
      }
      const isArchivedTab = activeTabRef.current === 'archived';
      setShifus(prev => {
        if (archiveTarget.archived && isArchivedTab) {
          return prev.filter(item => item.bid !== archiveTarget.bid);
        }
        if (!archiveTarget.archived && !isArchivedTab) {
          return prev.filter(item => item.bid !== archiveTarget.bid);
        }
        return prev.map(item =>
          item.bid === archiveTarget.bid
            ? { ...item, archived: !archiveTarget.archived }
            : item,
        );
      });
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t('common.core.unknownError');
      toast({
        title: message,
        variant: 'destructive',
      });
    } finally {
      setArchiveLoading(false);
      setArchiveDialogOpen(false);
      setArchiveTarget(null);
    }
  }, [archiveLoading, archiveTarget, canManageArchive, t, toast]);

  useEffect(() => {
    if (!hasResolvedAdminSession || !adminReady) {
      return;
    }
    resetListAndFetch();
  }, [
    activeTab,
    adminReady,
    hasResolvedAdminSession,
    i18n.language,
    resetListAndFetch,
  ]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !hasResolvedAdminSession || !adminReady) return;

    const observer = new IntersectionObserver(
      entries => {
        if (entries[0].isIntersecting && hasMore && fetchShifusRef.current) {
          fetchShifusRef.current();
        }
      },
      { threshold: 0.1 },
    );

    observer.observe(container);
    return () => observer.disconnect();
  }, [adminReady, hasMore, hasResolvedAdminSession]);

  // Centralized login check - redirect if not logged in after initialization
  useEffect(() => {
    if (isInitialized && !hasAuthenticatedAdminSession) {
      const currentPath = encodeURIComponent(
        window.location.pathname + window.location.search,
      );
      window.location.href = `/login?redirect=${currentPath}`;
      return;
    }
  }, [hasAuthenticatedAdminSession, isInitialized]);

  useEffect(() => {
    if (!hasResolvedAdminSession) {
      setAdminReady(false);
      return;
    }

    let cancelled = false;
    const ensureAdminPermissions = async () => {
      try {
        setError(null);
        await api.ensureAdminCreator({});
        if (!cancelled) {
          setAdminReady(true);
        }
      } catch (error) {
        console.error('Failed to ensure admin creator permissions:', error);
        if (!cancelled) {
          if (error instanceof ErrorWithCode) {
            setError({ message: error.message, code: error.code });
          } else {
            const message =
              error instanceof Error
                ? error.message
                : t('common.core.unknownError');
            setError({ message, code: 0 });
          }
          setAdminReady(false);
        }
      }
    };

    setAdminReady(false);
    ensureAdminPermissions();

    return () => {
      cancelled = true;
    };
  }, [hasResolvedAdminSession, permissionRetryNonce, t]);

  if (error) {
    return (
      <div className='h-full p-0'>
        <ErrorDisplay
          errorCode={error.code || 0}
          errorMessage={error.message}
          onRetry={() => {
            setError(null);
            setAdminReady(false);
            setPermissionRetryNonce(value => value + 1);
          }}
        />
      </div>
    );
  }

  return (
    <>
      <MobileUnsupportedDialog />
      <ShifuPermissionDialog
        open={permissionDialogOpen}
        onOpenChange={nextOpen => {
          setPermissionDialogOpen(nextOpen);
          if (!nextOpen) {
            setPermissionTarget(null);
          }
        }}
        shifu={
          permissionTarget
            ? {
                bid: permissionTarget.bid,
                created_user_bid: permissionTarget.created_user_bid,
              }
            : null
        }
      />
      <AlertDialog
        open={archiveDialogOpen}
        onOpenChange={open => {
          setArchiveDialogOpen(open);
          if (!open) {
            setArchiveTarget(null);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {archiveTarget?.archived
                ? t('module.shifuSetting.unarchiveTitle')
                : t('module.shifuSetting.archiveTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {archiveTarget?.archived
                ? t('module.shifuSetting.unarchiveConfirm')
                : t('module.shifuSetting.archiveConfirm')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={archiveLoading}>
              {t('common.core.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={event => {
                event.preventDefault();
                handleArchiveConfirm();
              }}
              disabled={archiveLoading}
            >
              {t('common.core.ok')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <div className='h-full p-0'>
        <div className='max-w-7xl mx-auto h-full overflow-hidden flex flex-col'>
          <AdminBreadcrumb items={[{ label: t('common.core.shifu') }]} />
          <AdminTitle title={t('common.core.shifu')} />
          <div className='mb-8 flex shrink-0 flex-col gap-4 lg:flex-row lg:items-center lg:justify-between'>
            <Tabs
              value={activeTab}
              onValueChange={value => setActiveTab(value as 'all' | 'archived')}
            >
              <TabsList className={COURSE_TABS_LIST_CLASS}>
                <TabsTrigger
                  value='all'
                  className={COURSE_TABS_TRIGGER_CLASS}
                >
                  {t('common.core.all')}
                </TabsTrigger>
                <TabsTrigger
                  value='archived'
                  className={COURSE_TABS_TRIGGER_CLASS}
                >
                  {t('common.core.archived')}
                </TabsTrigger>
              </TabsList>
            </Tabs>
            <div className='flex flex-col gap-3 sm:flex-row sm:items-center lg:justify-end'>
              <div
                className='flex flex-col gap-3 sm:flex-row sm:items-center'
                {...buildOnboardingTargetProps(
                  ONBOARDING_TARGET_IDS.courseCreationEntry,
                )}
              >
                {courseCreatorUrl ? (
                  <a
                    href={courseCreatorUrl}
                    target='_blank'
                    rel='noopener noreferrer'
                    className='text-xs text-muted-foreground underline hover:text-foreground'
                    {...buildOnboardingTargetProps(
                      ONBOARDING_TARGET_IDS.lobsterCreateEntry,
                    )}
                  >
                    {t('common.core.aiCourseCreator')}
                  </a>
                ) : null}
                <Button
                  size='sm'
                  onClick={handleCreateShifuModal}
                  {...buildOnboardingTargetProps(
                    ONBOARDING_TARGET_IDS.blankCreateEntry,
                  )}
                >
                  {t('common.core.createBlankShifu')}
                </Button>
              </div>
            </div>
          </div>
          <CreateShifuDialog
            open={showCreateShifuModal}
            onOpenChange={setShowCreateShifuModal}
            onSubmit={onCreateShifu}
          />
          <div className='flex-1 overflow-auto'>
            <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4'>
              {shifus.map(shifu => (
                <ShifuCard
                  id={shifu.bid + ''}
                  key={shifu.bid}
                  image={shifu.avatar}
                  title={shifu.name || ''}
                  description={shifu.description || ''}
                  isFavorite={shifu.is_favorite || false}
                  archived={Boolean(shifu.archived)}
                  canManageArchive={canManageArchive(shifu)}
                  canManagePermissions={canManagePermissions(shifu)}
                  onArchiveRequest={() => handleArchiveRequest(shifu)}
                  onPermissionRequest={() => handlePermissionRequest(shifu)}
                  onboardingTargetId={
                    shifu.bid === onboardingStatus?.guide_course.bid
                      ? guideCourseTargetId
                      : undefined
                  }
                />
              ))}
            </div>
            <div
              ref={containerRef}
              className='w-full h-10 flex items-center justify-center'
            >
              {loading && <Loading />}
              {!hasMore && shifus.length > 0 && (
                <p className='text-gray-500 text-sm'>
                  {t('common.core.noMoreShifus')}
                </p>
              )}
              {!loading && !hasMore && shifus.length === 0 && (
                <p className='text-gray-500 text-sm'>
                  {t('common.core.noShifus')}
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
};

export default ScriptManagementPage;
