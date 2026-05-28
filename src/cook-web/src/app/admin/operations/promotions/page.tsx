'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus } from 'lucide-react';
import api from '@/api';
import AdminClearableInput from '@/app/admin/components/AdminClearableInput';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import AdminFilter from '@/app/admin/components/AdminFilter';
import AdminBreadcrumb from '@/app/admin/components/AdminBreadcrumb';
import AdminTitle from '@/app/admin/components/AdminTitle';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import AdminRowActions from '@/app/admin/components/AdminRowActions';
import { ADMIN_TABLE_RESIZE_HANDLE_CLASS } from '@/app/admin/components/adminTableStyles';
import { useAdminResizableColumns } from '@/app/admin/hooks/useAdminResizableColumns';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import type {
  AdminPromotionCampaignItem,
  AdminPromotionCouponCodeItem,
  AdminPromotionCouponItem,
  AdminPromotionListResponse,
} from '@/app/admin/operations/operation-promotion-types';
import useOperatorGuard from '@/app/admin/operations/useOperatorGuard';
import ErrorDisplay from '@/components/ErrorDisplay';
import { Button } from '@/components/ui/Button';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { showDefaultToast, showErrorToast } from '@/hooks/useToast';
import { cn } from '@/lib/utils';
import {
  PromotionCampaignDialog,
  PromotionCouponDialog,
} from './PromotionFormDialogs';
import {
  PromotionCampaignRedemptionsDialog,
  PromotionCouponCodesDialog,
  PromotionCouponUsageDialog,
} from './PromotionRecordDialogs';
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
  EMPTY_VALUE,
  type ErrorState,
  PAGE_SIZE,
  type PromotionStatusChangeTarget,
  type PromotionTab,
  renderCouponAttentionBadges,
  renderPromotionStatusBadge,
  renderRuleLabel,
  renderTimeRange,
  renderTooltipText,
  resolveCampaignApplyTypeLabel,
  resolveCouponScopeLabel,
  resolveCouponUsageTypeLabel,
  SectionCard,
  shouldShowCampaignStatusToggle,
  shouldShowCouponStatusToggle,
  SINGLE_SELECT_ITEM_CLASS,
  TABLE_ACTION_CELL_CLASS,
  TABLE_ACTION_HEAD_CLASS,
  TABLE_CELL_CLASS,
  TABLE_HEAD_CLASS,
  TABLE_LAST_CELL_CLASS,
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
          <SectionCard
            title=''
            action={
              <Button
                size='sm'
                variant='outline'
                onClick={() => setCouponCreateOpen(true)}
              >
                <Plus className='mr-1 h-4 w-4' />
                {tPromotion('actions.createCoupon')}
              </Button>
            }
          >
            <AdminFilter
              items={couponFilterItems}
              expanded={couponFiltersExpanded}
              onExpandedChange={setCouponFiltersExpanded}
              onReset={handleCouponReset}
              onSearch={handleCouponSearch}
              resetLabel={t('module.order.filters.reset')}
              searchLabel={t('module.order.filters.search')}
              expandLabel={t('common.core.expand')}
              collapseLabel={t('common.core.collapse')}
              collapsedCount={4}
              className='bg-transparent'
              contentClassName='min-w-0'
              labelClassName='w-24 text-right'
              collapsedGridClassName='gap-x-5 xl:grid-cols-4'
              expandedGridClassName='gap-x-5 xl:grid-cols-3'
              labelColon
            />
          </SectionCard>
          {couponError ? (
            <ErrorDisplay
              errorMessage={couponError.message}
              errorCode={0}
            />
          ) : null}
          <AdminTableShell
            loading={couponLoading}
            isEmpty={!coupons.length}
            emptyContent={tPromotion('messages.emptyCoupons')}
            stickyActionEmpty={{
              contentColSpan:
                Object.keys(COUPON_DEFAULT_COLUMN_WIDTHS).length - 1,
              actionClassName: TABLE_ACTION_CELL_CLASS,
              actionStyle: getCouponColumnStyle('action'),
            }}
            withTooltipProvider
            tableWrapperClassName='max-h-[calc(100vh-18rem)] overflow-auto'
            table={emptyRow => (
              <Table containerClassName='overflow-visible max-h-none'>
                <TableHeader>
                  <TableRow>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('name')}
                    >
                      {tPromotion('table.name')}
                      {renderCouponResizeHandle('name')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('status')}
                    >
                      {tPromotion('table.status')}
                      {renderCouponResizeHandle('status')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('usageType')}
                    >
                      {tPromotion('table.usageType')}
                      {renderCouponResizeHandle('usageType')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('discountRule')}
                    >
                      {tPromotion('table.discountRule')}
                      {renderCouponResizeHandle('discountRule')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('code')}
                    >
                      {tPromotion('coupon.code')}
                      {renderCouponResizeHandle('code')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('scope')}
                    >
                      {tPromotion('table.scope')}
                      {renderCouponResizeHandle('scope')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('course')}
                    >
                      {tPromotion('table.course')}
                      {renderCouponResizeHandle('course')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('activeTime')}
                    >
                      {tPromotion('table.activeTime')}
                      {renderCouponResizeHandle('activeTime')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('usageProgress')}
                    >
                      {tPromotion('table.usageProgress')}
                      {renderCouponResizeHandle('usageProgress')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('codesEntry')}
                    >
                      {tPromotion('table.codesEntry')}
                      {renderCouponResizeHandle('codesEntry')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('couponBid')}
                    >
                      {tPromotion('table.couponBid')}
                      {renderCouponResizeHandle('couponBid')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('updatedAt')}
                    >
                      {tPromotion('table.updatedAt')}
                      {renderCouponResizeHandle('updatedAt')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('createdAt')}
                    >
                      {tPromotion('table.createdAt')}
                      {renderCouponResizeHandle('createdAt')}
                    </TableHead>
                    <TableHead
                      className={TABLE_ACTION_HEAD_CLASS}
                      style={getCouponColumnStyle('action')}
                    >
                      {tPromotion('table.actions')}
                      {renderCouponResizeHandle('action')}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {emptyRow}
                  {coupons.map(item => (
                    <TableRow key={item.coupon_bid}>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('name')}
                      >
                        {renderTooltipText(item.name)}
                      </TableCell>
                      <TableCell
                        className={cn(TABLE_CELL_CLASS, 'whitespace-normal')}
                        style={getCouponColumnStyle('status')}
                      >
                        <div className='flex flex-wrap items-center justify-center gap-1'>
                          {renderPromotionStatusBadge({
                            tPromotion,
                            statusKey: item.computed_status_key,
                            status: item.computed_status,
                          })}
                          {renderCouponAttentionBadges(item, tPromotion)}
                        </div>
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('usageType')}
                      >
                        {renderTooltipText(
                          resolveCouponUsageTypeLabel(
                            tPromotion,
                            item.usage_type,
                            item.usage_type_key,
                          ),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('discountRule')}
                      >
                        {renderTooltipText(
                          renderRuleLabel(
                            item.discount_type_key,
                            item.value,
                            currencySymbol,
                          ),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('code')}
                      >
                        {renderTooltipText(item.code)}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('scope')}
                      >
                        {renderTooltipText(
                          resolveCouponScopeLabel(tPromotion, item.scope_type),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('course')}
                      >
                        {renderTooltipText(
                          item.course_name ||
                            item.shifu_bid ||
                            tPromotion('scope.allCourses'),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('activeTime')}
                      >
                        {renderTooltipText(
                          renderTimeRange(item.start_at, item.end_at),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('usageProgress')}
                      >
                        <button
                          type='button'
                          className='text-primary transition-colors hover:text-primary/80 hover:underline'
                          onClick={() => {
                            setSelectedCouponBid(item.coupon_bid);
                            setSelectedCouponName(item.name || item.coupon_bid);
                            setSelectedCouponShowCourseColumn(
                              item.scope_type === 'all_courses',
                            );
                            setCouponUsageOpen(true);
                          }}
                        >
                          {renderTooltipText(
                            `${item.used_count}/${item.total_count}`,
                          )}
                        </button>
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('codesEntry')}
                      >
                        {Number(item.usage_type) === 802 ? (
                          <button
                            type='button'
                            className='text-primary transition-colors hover:text-primary/80 hover:underline'
                            onClick={() => {
                              setSelectedCouponBid(item.coupon_bid);
                              setSelectedCouponName(
                                item.name || item.coupon_bid,
                              );
                              setCouponCodesOpen(true);
                            }}
                          >
                            {tPromotion('table.codesEntry')}
                          </button>
                        ) : (
                          EMPTY_VALUE
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('couponBid')}
                      >
                        {renderTooltipText(item.coupon_bid)}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('updatedAt')}
                      >
                        {renderTooltipText(
                          formatAdminUtcDateTime(item.updated_at),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_LAST_CELL_CLASS}
                        style={getCouponColumnStyle('createdAt')}
                      >
                        {renderTooltipText(
                          formatAdminUtcDateTime(item.created_at),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_ACTION_CELL_CLASS}
                        style={getCouponColumnStyle('action')}
                      >
                        <div className='flex justify-center'>
                          <AdminRowActions
                            label={t('common.core.more')}
                            actions={[
                              {
                                key: 'edit',
                                label: tPromotion('actions.edit'),
                                onClick: () => void handleStartCouponEdit(item),
                              },
                              {
                                key: 'export-codes',
                                label: tPromotion('actions.exportCodes'),
                                hidden: Number(item.usage_type) !== 802,
                                onClick: () =>
                                  void handleCouponCodeExport(item),
                              },
                              {
                                key: 'toggle-status',
                                label:
                                  item.computed_status === 'inactive'
                                    ? tPromotion('actions.enable')
                                    : tPromotion('actions.disable'),
                                hidden: !shouldShowCouponStatusToggle(item),
                                onClick: () =>
                                  void handleCouponStatusToggle(item),
                              },
                            ]}
                          />
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            pagination={{
              pageIndex: couponPage,
              pageCount: couponPageCount,
              onPageChange: page => void fetchCoupons(page, couponFilters),
              prevLabel: t('module.order.paginationPrev'),
              nextLabel: t('module.order.paginationNext'),
              prevAriaLabel: t('module.order.paginationPrevAriaLabel'),
              nextAriaLabel: t('module.order.paginationNextAriaLabel'),
              hideWhenSinglePage: true,
            }}
            footerClassName='mt-3'
          />
        </TabsContent>

        <TabsContent
          value='campaigns'
          className='mt-6 space-y-6'
        >
          <SectionCard
            title=''
            action={
              <Button
                size='sm'
                variant='outline'
                onClick={() => setCampaignCreateOpen(true)}
              >
                <Plus className='mr-1 h-4 w-4' />
                {tPromotion('actions.createCampaign')}
              </Button>
            }
          >
            <AdminFilter
              items={campaignFilterItems}
              expanded={campaignFiltersExpanded}
              onExpandedChange={setCampaignFiltersExpanded}
              onReset={handleCampaignReset}
              onSearch={handleCampaignSearch}
              resetLabel={t('module.order.filters.reset')}
              searchLabel={t('module.order.filters.search')}
              expandLabel={t('common.core.expand')}
              collapseLabel={t('common.core.collapse')}
              collapsedCount={4}
              className='bg-transparent'
              contentClassName='min-w-0'
              labelClassName='w-24 text-right'
              collapsedGridClassName='gap-x-5 xl:grid-cols-4'
              expandedGridClassName='gap-x-5 xl:grid-cols-3'
              labelColon
            />
          </SectionCard>
          {campaignError ? (
            <ErrorDisplay
              errorMessage={campaignError.message}
              errorCode={0}
            />
          ) : null}
          <AdminTableShell
            loading={campaignLoading}
            isEmpty={!campaigns.length}
            emptyContent={tPromotion('messages.emptyCampaigns')}
            stickyActionEmpty={{
              contentColSpan:
                Object.keys(CAMPAIGN_DEFAULT_COLUMN_WIDTHS).length - 1,
              actionClassName: TABLE_ACTION_CELL_CLASS,
              actionStyle: getCampaignColumnStyle('action'),
            }}
            withTooltipProvider
            tableWrapperClassName='max-h-[calc(100vh-18rem)] overflow-auto'
            table={emptyRow => (
              <Table containerClassName='overflow-visible max-h-none'>
                <TableHeader>
                  <TableRow>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCampaignColumnStyle('name')}
                    >
                      {tPromotion('table.campaignName')}
                      {renderCampaignResizeHandle('name')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCampaignColumnStyle('status')}
                    >
                      {tPromotion('table.status')}
                      {renderCampaignResizeHandle('status')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCampaignColumnStyle('applyType')}
                    >
                      {tPromotion('table.applyType')}
                      {renderCampaignResizeHandle('applyType')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCampaignColumnStyle('channel')}
                    >
                      {tPromotion('table.channel')}
                      {renderCampaignResizeHandle('channel')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCampaignColumnStyle('course')}
                    >
                      {tPromotion('table.course')}
                      {renderCampaignResizeHandle('course')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCampaignColumnStyle('discountRule')}
                    >
                      {tPromotion('table.discountRule')}
                      {renderCampaignResizeHandle('discountRule')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCampaignColumnStyle('campaignTime')}
                    >
                      {tPromotion('filters.campaignTime')}
                      {renderCampaignResizeHandle('campaignTime')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCampaignColumnStyle('appliedOrderCount')}
                    >
                      {tPromotion('table.appliedOrderCount')}
                      {renderCampaignResizeHandle('appliedOrderCount')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCampaignColumnStyle('promoBid')}
                    >
                      {tPromotion('table.promoBid')}
                      {renderCampaignResizeHandle('promoBid')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCampaignColumnStyle('updatedAt')}
                    >
                      {tPromotion('table.updatedAt')}
                      {renderCampaignResizeHandle('updatedAt')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCampaignColumnStyle('createdAt')}
                    >
                      {tPromotion('table.createdAt')}
                      {renderCampaignResizeHandle('createdAt')}
                    </TableHead>
                    <TableHead
                      className={TABLE_ACTION_HEAD_CLASS}
                      style={getCampaignColumnStyle('action')}
                    >
                      {tPromotion('table.actions')}
                      {renderCampaignResizeHandle('action')}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {emptyRow}
                  {campaigns.map(item => (
                    <TableRow key={item.promo_bid}>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCampaignColumnStyle('name')}
                      >
                        {renderTooltipText(item.name)}
                      </TableCell>
                      <TableCell
                        className={cn(TABLE_CELL_CLASS, 'whitespace-normal')}
                        style={getCampaignColumnStyle('status')}
                      >
                        <div className='flex flex-wrap items-center justify-center gap-1'>
                          {renderPromotionStatusBadge({
                            tPromotion,
                            statusKey: item.computed_status_key,
                            status: item.computed_status,
                          })}
                        </div>
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCampaignColumnStyle('applyType')}
                      >
                        {renderTooltipText(
                          resolveCampaignApplyTypeLabel(
                            tPromotion,
                            item.apply_type,
                          ),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCampaignColumnStyle('channel')}
                      >
                        {renderTooltipText(item.channel)}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCampaignColumnStyle('course')}
                      >
                        {renderTooltipText(item.course_name || item.shifu_bid)}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCampaignColumnStyle('discountRule')}
                      >
                        {renderTooltipText(
                          renderRuleLabel(
                            item.discount_type_key,
                            item.value,
                            currencySymbol,
                          ),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCampaignColumnStyle('campaignTime')}
                      >
                        {renderTooltipText(
                          renderTimeRange(item.start_at, item.end_at),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCampaignColumnStyle('appliedOrderCount')}
                      >
                        <button
                          type='button'
                          className='inline-flex min-w-[2.5rem] items-center justify-center rounded-sm text-sm font-medium text-primary underline-offset-2 transition-colors hover:text-primary/80 hover:underline focus-visible:outline-none'
                          onClick={() =>
                            handleOpenCampaignRedemptions(
                              item.promo_bid,
                              item.name,
                            )
                          }
                          aria-label={`${tPromotion('actions.viewOrders')}: ${item.name || item.promo_bid}`}
                        >
                          {String(item.applied_order_count)}
                        </button>
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCampaignColumnStyle('promoBid')}
                      >
                        {renderTooltipText(item.promo_bid)}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCampaignColumnStyle('updatedAt')}
                      >
                        {renderTooltipText(
                          formatAdminUtcDateTime(item.updated_at),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_LAST_CELL_CLASS}
                        style={getCampaignColumnStyle('createdAt')}
                      >
                        {renderTooltipText(
                          formatAdminUtcDateTime(item.created_at),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_ACTION_CELL_CLASS}
                        style={getCampaignColumnStyle('action')}
                      >
                        <div className='flex justify-center'>
                          <AdminRowActions
                            label={t('common.core.more')}
                            actions={[
                              {
                                key: 'edit',
                                label: tPromotion('actions.edit'),
                                onClick: () =>
                                  void handleStartCampaignEdit(item),
                              },
                              {
                                key: 'toggle-status',
                                label:
                                  item.computed_status === 'inactive'
                                    ? tPromotion('actions.enable')
                                    : tPromotion('actions.disable'),
                                hidden: !shouldShowCampaignStatusToggle(item),
                                onClick: () =>
                                  void handleCampaignStatusToggle(item),
                              },
                            ]}
                          />
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            pagination={{
              pageIndex: campaignPage,
              pageCount: campaignPageCount,
              onPageChange: page => void fetchCampaigns(page, campaignFilters),
              prevLabel: t('module.order.paginationPrev'),
              nextLabel: t('module.order.paginationNext'),
              prevAriaLabel: t('module.order.paginationPrevAriaLabel'),
              nextAriaLabel: t('module.order.paginationNextAriaLabel'),
              hideWhenSinglePage: true,
            }}
            footerClassName='mt-3'
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
