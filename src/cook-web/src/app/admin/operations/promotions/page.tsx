'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminClearableInput from '@/app/admin/components/AdminClearableInput';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import AdminBreadcrumb from '@/app/admin/components/AdminBreadcrumb';
import AdminTitle from '@/app/admin/components/AdminTitle';
import { ADMIN_TABLE_RESIZE_HANDLE_CLASS } from '@/app/admin/components/adminTableStyles';
import { useAdminResizableColumns } from '@/app/admin/hooks/useAdminResizableColumns';
import type {
  AdminPromotionCampaignItem,
  AdminPromotionCouponCodeItem,
  AdminPromotionCouponItem,
  AdminPromotionListResponse,
} from '@/app/admin/operations/operation-promotion-types';
import useOperatorGuard from '@/app/admin/operations/useOperatorGuard';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { showDefaultToast, showErrorToast } from '@/hooks/useToast';
import {
  PromotionCampaignDialog,
  PromotionCouponDialog,
} from './PromotionFormDialogs';
import {
  PromotionCampaignRedemptionsDialog,
  PromotionCouponCodesDialog,
  PromotionCouponUsageDialog,
} from './PromotionRecordDialogs';
import PromotionCampaignsTab from './PromotionCampaignsTab';
import PromotionCouponsTab from './PromotionCouponsTab';
import PromotionStatusConfirmDialog from './PromotionStatusConfirmDialog';
import {
  ALL_OPTION_VALUE,
  CAMPAIGN_COLUMN_WIDTH_STORAGE_KEY,
  CAMPAIGN_DEFAULT_COLUMN_WIDTHS,
  type CampaignColumnKey,
  type CampaignFilters,
  type CampaignFormState,
  COLUMN_MAX_WIDTH,
  COLUMN_MIN_WIDTH,
  COUPON_COLUMN_WIDTH_STORAGE_KEY,
  COUPON_DEFAULT_COLUMN_WIDTHS,
  type CouponColumnKey,
  type CouponFilters,
  type CouponFormState,
  createDefaultCampaignFilters,
  createDefaultCouponFilters,
  type ErrorState,
  PAGE_SIZE,
  type PromotionStatusChangeTarget,
  type PromotionTab,
  SINGLE_SELECT_ITEM_CLASS,
  downloadExcelCompatibleCodesFile,
  canEditCampaignStrategyFields,
} from './promotionPageShared';

export default function AdminOperationPromotionsPage() {
  const { t } = useTranslation();
  const { t: tPromotion } = useTranslation('module.operationsPromotion');
  const { isReady } = useOperatorGuard();
  const currencySymbol = useEnvStore(
    (state: EnvStoreState) => state.currencySymbol || '',
  );
  const clearLabel = t('common.core.close');
  const [tab, setTab] = useState<PromotionTab>('coupons');
  const [couponLoading, setCouponLoading] = useState(true);
  const [campaignLoading, setCampaignLoading] = useState(false);
  const [couponError, setCouponError] = useState<ErrorState>(null);
  const [campaignError, setCampaignError] = useState<ErrorState>(null);
  const [coupons, setCoupons] = useState<AdminPromotionCouponItem[]>([]);
  const [campaigns, setCampaigns] = useState<AdminPromotionCampaignItem[]>([]);
  const [couponPage, setCouponPage] = useState(1);
  const [campaignPage, setCampaignPage] = useState(1);
  const [couponPageCount, setCouponPageCount] = useState(0);
  const [campaignPageCount, setCampaignPageCount] = useState(0);
  const [couponFilters, setCouponFilters] = useState<CouponFilters>(() =>
    createDefaultCouponFilters(),
  );
  const [campaignFilters, setCampaignFilters] = useState<CampaignFilters>(() =>
    createDefaultCampaignFilters(),
  );
  const campaignPageRef = useRef(campaignPage);
  const campaignFiltersRef = useRef(campaignFilters);
  const [couponCreateOpen, setCouponCreateOpen] = useState(false);
  const [editingCoupon, setEditingCoupon] =
    useState<AdminPromotionCouponItem | null>(null);
  const [campaignCreateOpen, setCampaignCreateOpen] = useState(false);
  const [editingCampaign, setEditingCampaign] = useState<{
    item: AdminPromotionCampaignItem;
    description: string;
  } | null>(null);
  const [selectedCouponBid, setSelectedCouponBid] = useState('');
  const [selectedCouponName, setSelectedCouponName] = useState('');
  const [selectedCouponShowCourseColumn, setSelectedCouponShowCourseColumn] =
    useState(false);
  const [couponCodesOpen, setCouponCodesOpen] = useState(false);
  const [selectedPromoBid, setSelectedPromoBid] = useState('');
  const [selectedPromoName, setSelectedPromoName] = useState('');
  const [couponUsageOpen, setCouponUsageOpen] = useState(false);
  const [campaignRedemptionsOpen, setCampaignRedemptionsOpen] = useState(false);
  const [pendingStatusChange, setPendingStatusChange] =
    useState<PromotionStatusChangeTarget | null>(null);
  const [statusChangeSubmitting, setStatusChangeSubmitting] = useState(false);
  const [couponFiltersExpanded, setCouponFiltersExpanded] = useState(false);
  const [campaignFiltersExpanded, setCampaignFiltersExpanded] = useState(false);
  const {
    getColumnStyle: getCouponColumnStyle,
    getResizeHandleProps: getCouponResizeHandleProps,
  } = useAdminResizableColumns<CouponColumnKey>({
    storageKey: COUPON_COLUMN_WIDTH_STORAGE_KEY,
    defaultWidths: COUPON_DEFAULT_COLUMN_WIDTHS,
    minWidth: COLUMN_MIN_WIDTH,
    maxWidth: COLUMN_MAX_WIDTH,
  });
  const {
    getColumnStyle: getCampaignColumnStyle,
    getResizeHandleProps: getCampaignResizeHandleProps,
  } = useAdminResizableColumns<CampaignColumnKey>({
    storageKey: CAMPAIGN_COLUMN_WIDTH_STORAGE_KEY,
    defaultWidths: CAMPAIGN_DEFAULT_COLUMN_WIDTHS,
    minWidth: COLUMN_MIN_WIDTH,
    maxWidth: COLUMN_MAX_WIDTH,
  });

  const renderCouponResizeHandle = (key: CouponColumnKey) => (
    <span
      className={ADMIN_TABLE_RESIZE_HANDLE_CLASS}
      {...getCouponResizeHandleProps(key)}
    />
  );

  const renderCampaignResizeHandle = (key: CampaignColumnKey) => (
    <span
      className={ADMIN_TABLE_RESIZE_HANDLE_CLASS}
      {...getCampaignResizeHandleProps(key)}
    />
  );

  const fetchCoupons = useCallback(
    async (pageIndex: number, filters: CouponFilters) => {
      setCouponLoading(true);
      setCouponError(null);
      try {
        const requestPayload = {
          page_index: pageIndex,
          page_size: PAGE_SIZE,
          keyword: filters.keyword.trim(),
          name: filters.name.trim(),
          course_query: filters.course_query.trim(),
          usage_type: filters.usage_type,
          ops_state: filters.ops_state,
          discount_type: filters.discount_type,
          status: filters.status,
          start_time: filters.start_time,
          end_time: filters.end_time,
        };
        let response = (await api.getAdminOperationPromotionCoupons(
          requestPayload,
        )) as AdminPromotionListResponse<AdminPromotionCouponItem>;
        const responsePage = response.page || pageIndex;
        const responsePageCount = response.page_count || 0;
        if (
          responsePageCount > 0 &&
          responsePage > responsePageCount &&
          (response.items || []).length === 0
        ) {
          response = (await api.getAdminOperationPromotionCoupons({
            ...requestPayload,
            page_index: responsePageCount,
          })) as AdminPromotionListResponse<AdminPromotionCouponItem>;
        }
        setCoupons(response.items || []);
        setCouponPage(response.page || 1);
        setCouponPageCount(response.page_count || 0);
      } catch (error) {
        setCouponError({
          message:
            (error as Error).message ||
            tPromotion('messages.loadCouponsFailed'),
        });
        setCoupons([]);
        setCouponPage(pageIndex);
        setCouponPageCount(0);
      } finally {
        setCouponLoading(false);
      }
    },
    [tPromotion],
  );

  const fetchCampaigns = useCallback(
    async (pageIndex: number, filters: CampaignFilters) => {
      setCampaignLoading(true);
      setCampaignError(null);
      try {
        const requestPayload = {
          page_index: pageIndex,
          page_size: PAGE_SIZE,
          keyword: filters.keyword.trim(),
          course_query: filters.course_query.trim(),
          apply_type: filters.apply_type,
          channel: filters.channel.trim(),
          discount_type: filters.discount_type,
          status: filters.status,
          start_time: filters.start_time,
          end_time: filters.end_time,
        };
        let response = (await api.getAdminOperationPromotionCampaigns(
          requestPayload,
        )) as AdminPromotionListResponse<AdminPromotionCampaignItem>;
        const responsePage = response.page || pageIndex;
        const responsePageCount = response.page_count || 0;
        if (
          responsePageCount > 0 &&
          responsePage > responsePageCount &&
          (response.items || []).length === 0
        ) {
          response = (await api.getAdminOperationPromotionCampaigns({
            ...requestPayload,
            page_index: responsePageCount,
          })) as AdminPromotionListResponse<AdminPromotionCampaignItem>;
        }
        setCampaigns(response.items || []);
        setCampaignPage(response.page || 1);
        setCampaignPageCount(response.page_count || 0);
      } catch (error) {
        setCampaignError({
          message:
            (error as Error).message ||
            tPromotion('messages.loadCampaignsFailed'),
        });
        setCampaigns([]);
        setCampaignPage(pageIndex);
        setCampaignPageCount(0);
      } finally {
        setCampaignLoading(false);
      }
    },
    [tPromotion],
  );

  useEffect(() => {
    if (!isReady) return;
    void fetchCoupons(1, createDefaultCouponFilters());
  }, [fetchCoupons, isReady]);

  campaignPageRef.current = campaignPage;
  campaignFiltersRef.current = campaignFilters;

  useEffect(() => {
    if (!isReady || tab !== 'campaigns') return;
    // Re-entering the tab should keep the operator on the same filtered page.
    void fetchCampaigns(campaignPageRef.current, campaignFiltersRef.current);
  }, [fetchCampaigns, isReady, tab]);

  const handleCouponSearch = () => void fetchCoupons(1, couponFilters);
  const handleCouponReset = () => {
    const next = createDefaultCouponFilters();
    setCouponFilters(next);
    void fetchCoupons(1, next);
  };
  const handleCampaignSearch = () => void fetchCampaigns(1, campaignFilters);
  const handleCampaignReset = () => {
    const next = createDefaultCampaignFilters();
    setCampaignFilters(next);
    void fetchCampaigns(1, next);
  };

  const handleCouponCreate = async (payload: CouponFormState) => {
    await api.createAdminOperationPromotionCoupon({
      name: payload.name.trim(),
      usage_type: Number(payload.usage_type),
      discount_type: Number(payload.discount_type),
      value: payload.value.trim(),
      total_count: Number(payload.total_count.trim()),
      code: payload.usage_type === '801' ? payload.code.trim() : '',
      scope_type: payload.scope_type,
      shifu_bid: payload.shifu_bid.trim(),
      start_at: payload.start_at,
      end_at: payload.end_at,
      enabled: payload.enabled === 'true',
    });
    showDefaultToast(tPromotion('messages.createSuccess'));
    await fetchCoupons(1, couponFilters);
  };

  const handleCouponUpdate = async (payload: CouponFormState) => {
    if (!editingCoupon) {
      return;
    }
    await api.updateAdminOperationPromotionCoupon({
      coupon_bid: editingCoupon.coupon_bid,
      name: payload.name.trim(),
      code: payload.usage_type === '801' ? payload.code.trim() : '',
      usage_type: Number(payload.usage_type),
      discount_type: Number(payload.discount_type),
      value: payload.value.trim(),
      total_count: Number(payload.total_count.trim()),
      scope_type: payload.scope_type,
      shifu_bid: payload.shifu_bid.trim(),
      start_at: payload.start_at,
      end_at: payload.end_at,
      enabled: payload.enabled === 'true',
    });
    showDefaultToast(tPromotion('messages.updateSuccess'));
    await fetchCoupons(couponPage, couponFilters);
    setEditingCoupon(null);
  };

  const handleCouponCodeExport = async (coupon: AdminPromotionCouponItem) => {
    if (Number(coupon.usage_type) !== 802) {
      return;
    }

    try {
      const allCodes: string[] = [];
      let nextPage = 1;
      let pageCount = 1;

      while (nextPage <= pageCount) {
        const response = (await api.getAdminOperationPromotionCouponCodes({
          coupon_bid: coupon.coupon_bid,
          page_index: nextPage,
          page_size: 100,
        })) as AdminPromotionListResponse<AdminPromotionCouponCodeItem>;
        (response.items || []).forEach(item => {
          if (item.code) {
            allCodes.push(item.code);
          }
        });
        pageCount = response.page_count || 0;
        nextPage += 1;
      }

      if (!allCodes.length) {
        showDefaultToast(tPromotion('messages.emptyCodes'));
        return;
      }

      const safeBaseName = (coupon.name || coupon.coupon_bid || 'coupon-codes')
        .trim()
        .replace(/[\\/:*?"<>|]+/g, '-');
      downloadExcelCompatibleCodesFile(
        `${safeBaseName}.xls`,
        tPromotion('coupon.code'),
        allCodes,
      );
      showDefaultToast(tPromotion('messages.exportSuccess'));
    } catch (error) {
      showErrorToast(
        (error as Error).message || tPromotion('messages.exportFailed'),
      );
    }
  };

  const handleCampaignCreate = async (payload: CampaignFormState) => {
    await api.createAdminOperationPromotionCampaign({
      name: payload.name.trim(),
      apply_type: Number(payload.apply_type),
      shifu_bid: payload.shifu_bid.trim(),
      discount_type: Number(payload.discount_type),
      value: payload.value.trim(),
      start_at: payload.start_at,
      end_at: payload.end_at,
      description: payload.description.trim(),
      channel: payload.channel.trim(),
      enabled: payload.enabled === 'true',
    });
    showDefaultToast(tPromotion('messages.createSuccess'));
    await fetchCampaigns(1, campaignFilters);
  };

  const handleCampaignUpdate = async (payload: CampaignFormState) => {
    if (!editingCampaign) {
      return;
    }
    await api.updateAdminOperationPromotionCampaign({
      promo_bid: editingCampaign.item.promo_bid,
      name: payload.name.trim(),
      apply_type: Number(payload.apply_type),
      shifu_bid: payload.shifu_bid.trim(),
      discount_type: Number(payload.discount_type),
      value: payload.value.trim(),
      start_at: payload.start_at,
      end_at: payload.end_at,
      description: payload.description.trim(),
      channel: payload.channel.trim(),
      enabled: payload.enabled === 'true',
    });
    showDefaultToast(tPromotion('messages.updateSuccess'));
    await fetchCampaigns(campaignPage, campaignFilters);
    setEditingCampaign(null);
  };

  const handleCouponStatusToggle = (item: AdminPromotionCouponItem) => {
    setPendingStatusChange({
      entityType: 'coupon',
      enabling: item.computed_status === 'inactive',
      item,
    });
  };

  const handleCampaignStatusToggle = (item: AdminPromotionCampaignItem) => {
    setPendingStatusChange({
      entityType: 'campaign',
      enabling: item.computed_status === 'inactive',
      item,
    });
  };

  const handleConfirmStatusToggle = async () => {
    if (!pendingStatusChange) {
      return;
    }

    setStatusChangeSubmitting(true);
    try {
      if (pendingStatusChange.entityType === 'coupon') {
        await api.updateAdminOperationPromotionCouponStatus({
          coupon_bid: pendingStatusChange.item.coupon_bid,
          enabled: pendingStatusChange.enabling,
        });
        showDefaultToast(
          pendingStatusChange.enabling
            ? tPromotion('messages.couponEnabledSuccess')
            : tPromotion('messages.couponDisabledSuccess'),
        );
        await fetchCoupons(couponPage, couponFilters);
      } else {
        await api.updateAdminOperationPromotionCampaignStatus({
          promo_bid: pendingStatusChange.item.promo_bid,
          enabled: pendingStatusChange.enabling,
        });
        showDefaultToast(
          pendingStatusChange.enabling
            ? tPromotion('messages.campaignEnabledSuccess')
            : tPromotion('messages.campaignDisabledSuccess'),
        );
        await fetchCampaigns(campaignPage, campaignFilters);
      }
      setPendingStatusChange(null);
    } catch (error) {
      showErrorToast((error as Error).message || t('common.core.submitFailed'));
    } finally {
      setStatusChangeSubmitting(false);
    }
  };

  const handleStartCouponEdit = useCallback(
    async (item: AdminPromotionCouponItem) => {
      try {
        const detail = (await api.getAdminOperationPromotionCouponDetail({
          coupon_bid: item.coupon_bid,
        })) as {
          coupon?: AdminPromotionCouponItem;
        };
        setEditingCoupon(detail.coupon || item);
      } catch (error) {
        showErrorToast(
          (error as Error).message ||
            tPromotion('messages.loadCouponDetailFailed'),
        );
      }
    },
    [tPromotion],
  );

  const handleOpenCampaignRedemptions = useCallback(
    (promoBid: string, campaignName: string) => {
      setSelectedPromoBid(promoBid);
      setSelectedPromoName(campaignName);
      setCampaignRedemptionsOpen(true);
    },
    [],
  );

  const handleStartCampaignEdit = useCallback(
    async (item: AdminPromotionCampaignItem) => {
      try {
        const detail = (await api.getAdminOperationPromotionCampaignDetail({
          promo_bid: item.promo_bid,
        })) as {
          campaign?: AdminPromotionCampaignItem;
          description?: string;
        };
        setEditingCampaign({
          item: detail.campaign || item,
          description: detail.description || '',
        });
      } catch (error) {
        showErrorToast(
          (error as Error).message ||
            tPromotion('messages.loadCampaignDetailFailed'),
        );
      }
    },
    [tPromotion],
  );

  const couponFilterItems = [
    {
      key: 'keyword',
      label: tPromotion('filters.keyword'),
      component: (
        <AdminClearableInput
          value={couponFilters.keyword}
          onChange={value =>
            setCouponFilters(current => ({ ...current, keyword: value }))
          }
          placeholder={tPromotion('filters.keywordPlaceholder')}
          clearLabel={clearLabel}
        />
      ),
    },
    {
      key: 'name',
      label: tPromotion('filters.name'),
      component: (
        <AdminClearableInput
          value={couponFilters.name}
          onChange={value =>
            setCouponFilters(current => ({ ...current, name: value }))
          }
          placeholder={tPromotion('filters.namePlaceholder')}
          clearLabel={clearLabel}
        />
      ),
    },
    {
      key: 'status',
      label: tPromotion('filters.status'),
      component: (
        <Select
          value={couponFilters.status || ALL_OPTION_VALUE}
          onValueChange={value =>
            setCouponFilters(current => ({
              ...current,
              status: value === ALL_OPTION_VALUE ? '' : value,
            }))
          }
        >
          <SelectTrigger className='h-9'>
            <SelectValue placeholder={tPromotion('filters.status')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem
              value={ALL_OPTION_VALUE}
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {t('common.core.all')}
            </SelectItem>
            <SelectItem
              value='not_started'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('status.notStarted')}
            </SelectItem>
            <SelectItem
              value='active'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('status.active')}
            </SelectItem>
            <SelectItem
              value='expired'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('status.expired')}
            </SelectItem>
            <SelectItem
              value='inactive'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('status.inactive')}
            </SelectItem>
          </SelectContent>
        </Select>
      ),
    },
    {
      key: 'course_query',
      label: tPromotion('filters.courseId'),
      component: (
        <AdminClearableInput
          value={couponFilters.course_query}
          onChange={value =>
            setCouponFilters(current => ({ ...current, course_query: value }))
          }
          placeholder={tPromotion('filters.courseIdPlaceholder')}
          clearLabel={clearLabel}
        />
      ),
    },
    {
      key: 'usage_type',
      label: tPromotion('filters.usageType'),
      component: (
        <Select
          value={couponFilters.usage_type || ALL_OPTION_VALUE}
          onValueChange={value =>
            setCouponFilters(current => ({
              ...current,
              usage_type: value === ALL_OPTION_VALUE ? '' : value,
            }))
          }
        >
          <SelectTrigger className='h-9'>
            <SelectValue placeholder={tPromotion('filters.usageType')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem
              value={ALL_OPTION_VALUE}
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {t('common.core.all')}
            </SelectItem>
            <SelectItem
              value='801'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('usageType.generic')}
            </SelectItem>
            <SelectItem
              value='802'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('usageType.singleUse')}
            </SelectItem>
          </SelectContent>
        </Select>
      ),
    },
    {
      key: 'ops_state',
      label: tPromotion('filters.opsState'),
      component: (
        <Select
          value={couponFilters.ops_state || ALL_OPTION_VALUE}
          onValueChange={value =>
            setCouponFilters(current => ({
              ...current,
              ops_state: value === ALL_OPTION_VALUE ? '' : value,
            }))
          }
        >
          <SelectTrigger className='h-9'>
            <SelectValue placeholder={tPromotion('filters.opsState')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem
              value={ALL_OPTION_VALUE}
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {t('common.core.all')}
            </SelectItem>
            <SelectItem
              value='expiring_soon'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('opsState.expiringSoon')}
            </SelectItem>
            <SelectItem
              value='used_up'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('opsState.usedUp')}
            </SelectItem>
          </SelectContent>
        </Select>
      ),
    },
    {
      key: 'discount_type',
      label: tPromotion('filters.discountType'),
      component: (
        <Select
          value={couponFilters.discount_type || ALL_OPTION_VALUE}
          onValueChange={value =>
            setCouponFilters(current => ({
              ...current,
              discount_type: value === ALL_OPTION_VALUE ? '' : value,
            }))
          }
        >
          <SelectTrigger className='h-9'>
            <SelectValue placeholder={tPromotion('filters.discountType')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem
              value={ALL_OPTION_VALUE}
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {t('common.core.all')}
            </SelectItem>
            <SelectItem
              value='701'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('discountType.fixed')}
            </SelectItem>
            <SelectItem
              value='702'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('discountType.percent')}
            </SelectItem>
          </SelectContent>
        </Select>
      ),
    },
    {
      key: 'active_time',
      label: tPromotion('filters.activeTime'),
      component: (
        <AdminDateRangeFilter
          startValue={couponFilters.start_time}
          endValue={couponFilters.end_time}
          onChange={range =>
            setCouponFilters(current => ({
              ...current,
              start_time: range.start,
              end_time: range.end,
            }))
          }
          placeholder={tPromotion('filters.activeTime')}
          resetLabel={t('module.order.filters.reset')}
          clearLabel={clearLabel}
        />
      ),
    },
  ];

  const campaignFilterItems = [
    {
      key: 'keyword',
      label: tPromotion('filters.campaignName'),
      component: (
        <AdminClearableInput
          value={campaignFilters.keyword}
          onChange={value =>
            setCampaignFilters(current => ({ ...current, keyword: value }))
          }
          placeholder={tPromotion('filters.campaignNamePlaceholder')}
          clearLabel={clearLabel}
        />
      ),
    },
    {
      key: 'course_query',
      label: tPromotion('filters.courseId'),
      component: (
        <AdminClearableInput
          value={campaignFilters.course_query}
          onChange={value =>
            setCampaignFilters(current => ({ ...current, course_query: value }))
          }
          placeholder={tPromotion('filters.courseIdPlaceholder')}
          clearLabel={clearLabel}
        />
      ),
    },
    {
      key: 'status',
      label: tPromotion('filters.status'),
      component: (
        <Select
          value={campaignFilters.status || ALL_OPTION_VALUE}
          onValueChange={value =>
            setCampaignFilters(current => ({
              ...current,
              status: value === ALL_OPTION_VALUE ? '' : value,
            }))
          }
        >
          <SelectTrigger className='h-9'>
            <SelectValue placeholder={tPromotion('filters.status')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem
              value={ALL_OPTION_VALUE}
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {t('common.core.all')}
            </SelectItem>
            <SelectItem
              value='not_started'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('status.notStarted')}
            </SelectItem>
            <SelectItem
              value='active'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('status.active')}
            </SelectItem>
            <SelectItem
              value='ended'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('status.ended')}
            </SelectItem>
            <SelectItem
              value='inactive'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('status.inactive')}
            </SelectItem>
          </SelectContent>
        </Select>
      ),
    },
    {
      key: 'apply_type',
      label: tPromotion('campaign.applyType'),
      component: (
        <Select
          value={campaignFilters.apply_type || ALL_OPTION_VALUE}
          onValueChange={value =>
            setCampaignFilters(current => ({
              ...current,
              apply_type: value === ALL_OPTION_VALUE ? '' : value,
            }))
          }
        >
          <SelectTrigger className='h-9'>
            <SelectValue
              placeholder={tPromotion('campaign.applyTypePlaceholder')}
            />
          </SelectTrigger>
          <SelectContent>
            <SelectItem
              value={ALL_OPTION_VALUE}
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {t('common.core.all')}
            </SelectItem>
            <SelectItem
              value='2101'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('campaign.applyTypeAuto')}
            </SelectItem>
            <SelectItem
              value='2102'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('campaign.applyTypeEvent')}
            </SelectItem>
            <SelectItem
              value='2103'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('campaign.applyTypeManual')}
            </SelectItem>
          </SelectContent>
        </Select>
      ),
    },
    {
      key: 'channel',
      label: tPromotion('campaign.channel'),
      component: (
        <AdminClearableInput
          value={campaignFilters.channel}
          onChange={value =>
            setCampaignFilters(current => ({ ...current, channel: value }))
          }
          placeholder={tPromotion('campaign.channelPlaceholder')}
          clearLabel={clearLabel}
        />
      ),
    },
    {
      key: 'discount_type',
      label: tPromotion('filters.discountType'),
      component: (
        <Select
          value={campaignFilters.discount_type || ALL_OPTION_VALUE}
          onValueChange={value =>
            setCampaignFilters(current => ({
              ...current,
              discount_type: value === ALL_OPTION_VALUE ? '' : value,
            }))
          }
        >
          <SelectTrigger className='h-9'>
            <SelectValue placeholder={tPromotion('filters.discountType')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem
              value={ALL_OPTION_VALUE}
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {t('common.core.all')}
            </SelectItem>
            <SelectItem
              value='701'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('discountType.fixed')}
            </SelectItem>
            <SelectItem
              value='702'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('discountType.percent')}
            </SelectItem>
          </SelectContent>
        </Select>
      ),
    },
    {
      key: 'campaign_time',
      label: tPromotion('filters.campaignTime'),
      component: (
        <AdminDateRangeFilter
          startValue={campaignFilters.start_time}
          endValue={campaignFilters.end_time}
          onChange={range =>
            setCampaignFilters(current => ({
              ...current,
              start_time: range.start,
              end_time: range.end,
            }))
          }
          placeholder={tPromotion('filters.campaignTime')}
          resetLabel={t('module.order.filters.reset')}
          clearLabel={clearLabel}
        />
      ),
    },
  ];

  if (!isReady) {
    return null;
  }

  return (
    <div className='pb-6'>
      <AdminBreadcrumb items={[{ label: tPromotion('title') }]} />
      <Tabs
        value={tab}
        onValueChange={value => setTab(value as PromotionTab)}
      >
        <AdminTitle
          title={tPromotion('title')}
          tabs={
            <TabsList className='h-9'>
              <TabsTrigger value='coupons'>
                {tPromotion('tabs.coupons')}
              </TabsTrigger>
              <TabsTrigger value='campaigns'>
                {tPromotion('tabs.campaigns')}
              </TabsTrigger>
            </TabsList>
          }
        />

        <TabsContent
          value='coupons'
          className='mt-6 space-y-6'
        >
          <PromotionCouponsTab
            t={t}
            tPromotion={tPromotion}
            currencySymbol={currencySymbol}
            filterItems={couponFilterItems}
            filtersExpanded={couponFiltersExpanded}
            onFiltersExpandedChange={setCouponFiltersExpanded}
            onReset={handleCouponReset}
            onSearch={handleCouponSearch}
            onCreate={() => setCouponCreateOpen(true)}
            error={couponError}
            loading={couponLoading}
            coupons={coupons}
            page={couponPage}
            pageCount={couponPageCount}
            filters={couponFilters}
            fetchCoupons={fetchCoupons}
            getColumnStyle={getCouponColumnStyle}
            renderResizeHandle={renderCouponResizeHandle}
            onOpenUsage={item => {
              setSelectedCouponBid(item.coupon_bid);
              setSelectedCouponName(item.name || item.coupon_bid);
              setSelectedCouponShowCourseColumn(
                item.scope_type === 'all_courses',
              );
              setCouponUsageOpen(true);
            }}
            onOpenCodes={item => {
              setSelectedCouponBid(item.coupon_bid);
              setSelectedCouponName(item.name || item.coupon_bid);
              setCouponCodesOpen(true);
            }}
            onEdit={handleStartCouponEdit}
            onExportCodes={handleCouponCodeExport}
            onToggleStatus={handleCouponStatusToggle}
          />
        </TabsContent>

        <TabsContent
          value='campaigns'
          className='mt-6 space-y-6'
        >
          <PromotionCampaignsTab
            t={t}
            tPromotion={tPromotion}
            currencySymbol={currencySymbol}
            filterItems={campaignFilterItems}
            filtersExpanded={campaignFiltersExpanded}
            onFiltersExpandedChange={setCampaignFiltersExpanded}
            onReset={handleCampaignReset}
            onSearch={handleCampaignSearch}
            onCreate={() => setCampaignCreateOpen(true)}
            error={campaignError}
            loading={campaignLoading}
            campaigns={campaigns}
            page={campaignPage}
            pageCount={campaignPageCount}
            filters={campaignFilters}
            fetchCampaigns={fetchCampaigns}
            getColumnStyle={getCampaignColumnStyle}
            renderResizeHandle={renderCampaignResizeHandle}
            onOpenRedemptions={handleOpenCampaignRedemptions}
            onEdit={handleStartCampaignEdit}
            onToggleStatus={handleCampaignStatusToggle}
          />
        </TabsContent>
      </Tabs>

      <PromotionCouponDialog
        open={couponCreateOpen}
        onOpenChange={setCouponCreateOpen}
        onSubmit={handleCouponCreate}
      />
      <PromotionCouponDialog
        open={Boolean(editingCoupon)}
        onOpenChange={open => {
          if (!open) {
            setEditingCoupon(null);
          }
        }}
        onSubmit={handleCouponUpdate}
        coupon={editingCoupon}
      />
      <PromotionCampaignDialog
        open={campaignCreateOpen}
        onOpenChange={setCampaignCreateOpen}
        onSubmit={handleCampaignCreate}
      />
      <PromotionCampaignDialog
        open={Boolean(editingCampaign)}
        onOpenChange={open => {
          if (!open) {
            setEditingCampaign(null);
          }
        }}
        onSubmit={handleCampaignUpdate}
        campaign={editingCampaign}
        strategyEditable={
          editingCampaign
            ? canEditCampaignStrategyFields(editingCampaign.item)
            : false
        }
      />
      <PromotionCouponUsageDialog
        open={couponUsageOpen}
        onOpenChange={open => {
          setCouponUsageOpen(open);
          if (!open) {
            setSelectedCouponBid('');
            setSelectedCouponName('');
            setSelectedCouponShowCourseColumn(false);
          }
        }}
        couponBid={selectedCouponBid}
        couponName={selectedCouponName}
        showCourseColumn={selectedCouponShowCourseColumn}
      />
      <PromotionCouponCodesDialog
        open={couponCodesOpen}
        onOpenChange={open => {
          setCouponCodesOpen(open);
          if (!open) {
            setSelectedCouponBid('');
            setSelectedCouponName('');
          }
        }}
        couponBid={selectedCouponBid}
        couponName={selectedCouponName}
      />
      <PromotionCampaignRedemptionsDialog
        open={campaignRedemptionsOpen}
        onOpenChange={open => {
          setCampaignRedemptionsOpen(open);
          if (!open) {
            setSelectedPromoBid('');
            setSelectedPromoName('');
          }
        }}
        promoBid={selectedPromoBid}
        campaignName={selectedPromoName}
      />
      <PromotionStatusConfirmDialog
        changeTarget={pendingStatusChange}
        submitting={statusChangeSubmitting}
        onOpenChange={open => {
          if (!open && !statusChangeSubmitting) {
            setPendingStatusChange(null);
          }
        }}
        onConfirm={handleConfirmStatusToggle}
      />
    </div>
  );
}
