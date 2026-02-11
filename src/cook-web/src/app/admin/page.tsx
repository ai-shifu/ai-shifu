'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { PlusIcon } from '@heroicons/react/24/outline';
import { TrophyIcon, StarIcon } from '@heroicons/react/24/solid';
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
import { useUserStore } from '@/store';
import { useTracking } from '@/c-common/hooks/useTracking';
import { canManageArchive as canManageArchiveForShifu } from '@/lib/shifu-permissions';
interface ShifuCardProps {
  id: string;
  image: string | undefined;
  title: string;
  description: string;
  isFavorite: boolean;
  archived?: boolean;
  canManageArchive?: boolean;
  onArchiveRequest?: () => void;
}

const CARD_CONTAINER_CLASS =
  'w-full h-full min-h-[118px] rounded-xl border border-slate-200 bg-background shadow-[0_4px_20px_rgba(15,23,42,0.08)] transition-all duration-200 ease-in-out hover:shadow-[0_10px_30px_rgba(15,23,42,0.12)]';
const CARD_CONTENT_CLASS = 'p-4 flex flex-col gap-2 h-full cursor-pointer';

const ShifuCard = ({
  id,
  image,
  title,
  description,
  isFavorite,
  archived,
  canManageArchive,
  onArchiveRequest,
}: ShifuCardProps) => {
  const { t } = useTranslation();
  return (
    <div className='relative w-full h-full'>
      <Link
        href={`/shifu/${id}`}
        className='block w-full h-full'
      >
        <Card className={CARD_CONTAINER_CLASS}>
          <CardContent className={CARD_CONTENT_CLASS}>
            <div className='flex flex-row items-center justify-between'>
              <div className='flex flex-row items-center mb-2 w-full'>
                <div className='p-2 h-10 w-10 rounded-lg bg-primary/10 mr-4 flex items-center justify-center shrink-0'>
                  {image && (
                    <img
                      src={image}
                      alt='recipe'
                      className='w-full h-full object-cover rounded-lg'
                    />
                  )}
                  {!image && <TrophyIcon className='w-6 h-6 text-primary' />}
                </div>

                <h3 className='font-medium text-gray-900 leading-5 whitespace-nowrap overflow-hidden text-ellipsis'>
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
            <p className='text-sm text-gray-500 line-clamp-3 break-words break-all min-h-[1.25rem]'>
              {description || ''}
            </p>
          </CardContent>
        </Card>
      </Link>
      {canManageArchive && (
        <DropdownMenu>
          {/* Reveal the menu only when hovering the top-right hotspot to avoid overlapping the archive badge. */}
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
  const currentUserId = useUserStore(state => state.userInfo?.user_id || '');
  const [adminReady, setAdminReady] = useState(false);
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
  const pageSize = 30;
  const currentPage = useRef(1);
  const containerRef = useRef(null);
  const fetchShifusRef = useRef<(() => Promise<void>) | null>(null);
  const loadingRef = useRef(false);
  const hasMoreRef = useRef(true);
  const listVersionRef = useRef(0);

  const activeTabRef = useRef<'all' | 'archived'>(activeTab);

  useEffect(() => {
    activeTabRef.current = activeTab;
  }, [activeTab]);

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

  const handleArchiveRequest = useCallback((shifu: Shifu) => {
    setArchiveTarget(shifu);
    setArchiveDialogOpen(true);
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
    if (!isInitialized || !adminReady) {
      return;
    }
    resetListAndFetch();
  }, [activeTab, i18n.language, isInitialized, adminReady, resetListAndFetch]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !isInitialized || !adminReady) return;

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
  }, [hasMore, isInitialized, adminReady]);

  // Centralized login check - redirect if not logged in after initialization
  useEffect(() => {
    if (isInitialized && isGuest) {
      const currentPath = encodeURIComponent(
        window.location.pathname + window.location.search,
      );
      window.location.href = `/login?redirect=${currentPath}`;
      return;
    }
  }, [isInitialized, isGuest]);

  useEffect(() => {
    if (!isInitialized) {
      return;
    }
    if (isGuest) {
      setAdminReady(false);
      return;
    }

    let cancelled = false;
    const ensureAdminPermissions = async () => {
      try {
        await api.ensureAdminCreator({});
      } catch (error) {
        console.error('Failed to ensure admin creator permissions:', error);
      } finally {
        if (!cancelled) {
          setAdminReady(true);
        }
      }
    };

    setAdminReady(false);
    ensureAdminPermissions();

    return () => {
      cancelled = true;
    };
  }, [isInitialized, isGuest]);

  if (error) {
    return (
      <div className='h-full p-0'>
        <ErrorDisplay
          errorCode={error.code || 0}
          errorMessage={error.message}
          onRetry={() => {
            resetListAndFetch();
          }}
        />
      </div>
    );
  }

  return (
    <>
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
          <div className='mb-3'>
            <h1 className='text-2xl font-semibold text-gray-900'>
              {t('common.core.shifu')}
            </h1>
          </div>
          <div className='flex items-center gap-3 mb-5'>
            <Button
              size='sm'
              variant='outline'
              onClick={handleCreateShifuModal}
            >
              <PlusIcon className='w-5 h-5 mr-1' />
              {t('common.core.createBlankShifu')}
            </Button>
            <Tabs
              value={activeTab}
              onValueChange={value => setActiveTab(value as 'all' | 'archived')}
            >
              <TabsList className='h-9 rounded-full bg-muted/40'>
                <TabsTrigger value='all'>{t('common.core.all')}</TabsTrigger>
                <TabsTrigger value='archived'>
                  {t('common.core.archived')}
                </TabsTrigger>
              </TabsList>
            </Tabs>
            <CreateShifuDialog
              open={showCreateShifuModal}
              onOpenChange={setShowCreateShifuModal}
              onSubmit={onCreateShifu}
            />
          </div>
          <div className='flex-1 overflow-auto'>
            <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-3'>
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
                  onArchiveRequest={() => handleArchiveRequest(shifu)}
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
