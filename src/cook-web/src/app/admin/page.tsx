'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import Link from 'next/link';
import {
  PlusIcon,
  StarIcon as StarOutlineIcon,
  RectangleStackIcon as RectangleStackOutlineIcon,
} from '@heroicons/react/24/outline';
import {
  TrophyIcon,
  RectangleStackIcon,
  StarIcon,
} from '@heroicons/react/24/solid';
import api from '@/api';
import { Shifu } from '@/types/shifu';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { Button } from '@/components/ui/Button';
import { Card, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { CreateShifuDialog } from '@/components/create-shifu-dialog';
import { useToast } from '@/hooks/useToast';
import { useRouter } from 'next/navigation';
import Loading from '@/components/loading';
import { useTranslation } from 'react-i18next';
import { ErrorWithCode } from '@/lib/request';
import ErrorDisplay from '@/components/ErrorDisplay';
import { useUserStore } from '@/store';
import { useTracking } from '@/c-common/hooks/useTracking';
interface ShifuCardProps {
  id: string;
  image: string | undefined;
  title: string;
  description: string;
  isFavorite: boolean;
  archived?: boolean;
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
}: ShifuCardProps) => {
  const { t } = useTranslation();
  return (
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
            </div>
            <div className='flex items-center gap-2'>
              {isFavorite && <StarIcon className='w-5 h-5 text-yellow-400' />}
              {archived && (
                <Badge className='rounded-full bg-muted text-muted-foreground px-3 py-0 text-xs whitespace-nowrap'>
                  {t('common.core.archived')}
                </Badge>
              )}
            </div>
          </div>
          <p className='text-sm text-gray-500 line-clamp-3 break-words break-all min-h-[1.25rem]'>
            {description || ''}
          </p>
        </CardContent>
      </Card>
    </Link>
  );
};

const ScriptManagementPage = () => {
  const router = useRouter();
  const { toast } = useToast();
  const { trackEvent } = useTracking();
  const { t, i18n } = useTranslation();
  const isInitialized = useUserStore(state => state.isInitialized);
  const isGuest = useUserStore(state => state.isGuest);
  const [adminReady, setAdminReady] = useState(false);
  const [activeTab, setActiveTab] = useState<'all' | 'archived'>('all');
  const [shifus, setShifus] = useState<Shifu[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [showCreateShifuModal, setShowCreateShifuModal] = useState(false);
  const [error, setError] = useState<{ message: string; code?: number } | null>(
    null,
  );
  const pageSize = 30;
  const currentPage = useRef(1);
  const containerRef = useRef(null);
  const fetchShifusRef = useRef<(() => Promise<void>) | null>(null);

  const activeTabRef = useRef<'all' | 'archived'>(activeTab);

  useEffect(() => {
    activeTabRef.current = activeTab;
  }, [activeTab]);

  const fetchShifus = useCallback(async () => {
    if (loading || !hasMore) return;

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

      if (requestTab !== activeTabRef.current) {
        setLoading(false);
        return;
      }
      if (items.length < pageSize) {
        setHasMore(false);
      }

      setShifus(prev => {
        // Prevent duplicate records
        const existingIds = new Set(prev.map(shifu => shifu.bid));
        const newItems = items.filter(
          (item: Shifu) => !existingIds.has(item.bid),
        );
        return [...prev, ...newItems];
      });
      currentPage.current += 1;
      setLoading(false);
    } catch (error: any) {
      console.error('Failed to fetch shifus:', error);
      setLoading(false);
      if (error instanceof ErrorWithCode) {
        // Pass the error code and original message to ErrorDisplay
        // ErrorDisplay will handle the translation based on error code
        setError({ message: error.message, code: error.code });
      } else {
        // For unknown errors, pass a generic error code
        setError({ message: error.message || 'Unknown error', code: 0 });
      }
    }
  }, [loading, hasMore, activeTab]);

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

  useEffect(() => {
    if (!isInitialized || !adminReady) return;
    setShifus([]);
    setHasMore(true);
    currentPage.current = 1;
    setError(null);
    if (fetchShifusRef.current) {
      fetchShifusRef.current();
    }
  }, [activeTab, isInitialized, adminReady]);

  // Reload list when language changes to reflect localized fields
  useEffect(() => {
    setShifus([]);
    setHasMore(true);
    currentPage.current = 1;
    setError(null);
    if (isInitialized && adminReady && fetchShifusRef.current) {
      fetchShifusRef.current();
    }
  }, [i18n.language, isInitialized, adminReady]);

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

  // Fetch data when user is initialized
  useEffect(() => {
    if (isInitialized && adminReady && fetchShifusRef.current) {
      if (shifus.length === 0 && !loading) {
        fetchShifusRef.current();
      }
    }
  }, [isInitialized, adminReady, shifus.length, loading]);

  if (error) {
    return (
      <div className='h-full p-0'>
        <ErrorDisplay
          errorCode={error.code || 0}
          errorMessage={error.message}
          onRetry={() => {
            setError(null);
            setShifus([]);
            setHasMore(true);
            currentPage.current = 1;
            fetchShifus();
          }}
        />
      </div>
    );
  }

  return (
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
            {!loading && !hasMore && shifus.length == 0 && (
              <p className='text-gray-500 text-sm'>
                {t('common.core.noShifus')}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ScriptManagementPage;
