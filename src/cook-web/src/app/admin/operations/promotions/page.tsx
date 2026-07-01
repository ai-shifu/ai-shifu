'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus } from 'lucide-react';
import api from '@/api';
import AdminClearableInput from '@/app/admin/components/AdminClearableInput';
import AdminFilter from '@/app/admin/components/AdminFilter';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import AdminBreadcrumb from '@/app/admin/components/AdminBreadcrumb';
import AdminTitle from '@/app/admin/components/AdminTitle';
import AdminRowActions from '@/app/admin/components/AdminRowActions';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import { ADMIN_TABLE_RESIZE_HANDLE_CLASS } from '@/app/admin/components/adminTableStyles';
import { useAdminResizableColumns } from '@/app/admin/hooks/useAdminResizableColumns';
import type {
  AdminBillingCampaignDetail,
  AdminBillingCampaignItem,
  AdminBillingCampaignProductOptions,
  AdminPromotionCampaignItem,
  AdminPromotionCouponCodeItem,
  AdminPromotionCouponItem,
  AdminPromotionListResponse,
  AdminReferralCampaignDetail,
  AdminReferralCampaignItem,
} from '@/app/admin/operations/operation-promotion-types';
import useOperatorGuard from '@/app/admin/operations/useOperatorGuard';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';
import ErrorDisplay from '@/components/ErrorDisplay';
import { Button } from '@/components/ui/Button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { showDefaultToast, showErrorToast } from '@/hooks/useToast';
import { cn } from '@/lib/utils';
import {
  PackageCampaignDialog,
  PromotionCampaignDialog,
  PromotionCouponDialog,
  ReferralCampaignDialog,
} from './PromotionFormDialogs';
import {
  PackageCampaignProductDetailsDialog,
  PromotionCampaignRedemptionsDialog,
  PromotionCouponCodesDialog,
  PromotionCouponUsageDialog,
} from './PromotionRecordDialogs';
import PromotionCampaignsTab from './PromotionCampaignsTab';
import PromotionCouponsTab from './PromotionCouponsTab';
import ReferralCampaignsTab from './ReferralCampaignsTab';
import PromotionStatusConfirmDialog from './PromotionStatusConfirmDialog';
import {
  ALL_OPTION_VALUE,
  buildReferralCampaignPayload,
  CAMPAIGN_COLUMN_WIDTH_STORAGE_KEY,
  CAMPAIGN_DEFAULT_COLUMN_WIDTHS,
  type CampaignColumnKey,
  type CampaignFilters,
  type CampaignFormState,
  buildPackageCampaignProductsPayload,
  COLUMN_MAX_WIDTH,
  COLUMN_MIN_WIDTH,
  COUPON_COLUMN_WIDTH_STORAGE_KEY,
  COUPON_DEFAULT_COLUMN_WIDTHS,
  COUPON_OPS_STATE_OPTIONS,
  type CouponColumnKey,
  type CouponFilters,
  type CouponFormState,
  createDefaultCampaignFilters,
  createDefaultCouponFilters,
  createDefaultPackageCampaignFilters,
  createDefaultReferralCampaignFilters,
  type ErrorState,
  PAGE_SIZE,
  PACKAGE_CAMPAIGN_COLUMN_WIDTH_STORAGE_KEY,
  PACKAGE_CAMPAIGN_DEFAULT_COLUMN_WIDTHS,
  type PackageCampaignColumnKey,
  type PackageCampaignFilters,
  type PackageCampaignFormState,
  REFERRAL_CAMPAIGN_COLUMN_WIDTH_STORAGE_KEY,
  REFERRAL_CAMPAIGN_DEFAULT_COLUMN_WIDTHS,
  type ReferralCampaignColumnKey,
  type ReferralCampaignFilters,
  type ReferralCampaignFormState,
  type PromotionStatusChangeTarget,
  type PromotionTab,
  renderPromotionStatusBadge,
  renderTimeRange,
  renderTooltipText,
  resolvePackageCampaignBenefitTypeLabel,
  resolvePackageCampaignProductSummary,
  resolvePackageCampaignProductTypeLabel,
  resolvePackageCampaignRuleLabel,
  SectionCard,
  shouldShowPackageCampaignStatusToggle,
  TABLE_ACTION_CELL_CLASS,
  TABLE_ACTION_HEAD_CLASS,
  TABLE_CELL_CLASS,
  TABLE_HEAD_CLASS,
  SINGLE_SELECT_ITEM_CLASS,
  downloadExcelCompatibleCodesFile,
  canEditCampaignStrategyFields,
} from './promotionPageShared';

/**
 * t('module.operationsPromotion.actions.createReferralCampaign')
 * t('module.operationsPromotion.messages.emptyReferralCampaigns')
 * t('module.operationsPromotion.referralCampaign.cap')
 * t('module.operationsPromotion.referralCampaign.capSummary')
 * t('module.operationsPromotion.referralCampaign.relationCount')
 * t('module.operationsPromotion.referralCampaign.rewardCount')
 * t('module.operationsPromotion.referralCampaign.validityDaysValue')
 */
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
  const [packageCampaignLoading, setPackageCampaignLoading] = useState(false);
  const [referralCampaignLoading, setReferralCampaignLoading] = useState(false);
  const [couponError, setCouponError] = useState<ErrorState>(null);
  const [campaignError, setCampaignError] = useState<ErrorState>(null);
  const [packageCampaignError, setPackageCampaignError] =
    useState<ErrorState>(null);
  const [referralCampaignError, setReferralCampaignError] =
    useState<ErrorState>(null);
  const [coupons, setCoupons] = useState<AdminPromotionCouponItem[]>([]);
  const [campaigns, setCampaigns] = useState<AdminPromotionCampaignItem[]>([]);
  const [packageCampaigns, setPackageCampaigns] = useState<
    AdminBillingCampaignItem[]
  >([]);
  const [referralCampaigns, setReferralCampaigns] = useState<
    AdminReferralCampaignItem[]
  >([]);
  const [couponPage, setCouponPage] = useState(1);
  const [campaignPage, setCampaignPage] = useState(1);
  const [packageCampaignPage, setPackageCampaignPage] = useState(1);
  const [referralCampaignPage, setReferralCampaignPage] = useState(1);
  const [couponPageCount, setCouponPageCount] = useState(0);
  const [campaignPageCount, setCampaignPageCount] = useState(0);
  const [packageCampaignPageCount, setPackageCampaignPageCount] = useState(0);
  const [referralCampaignPageCount, setReferralCampaignPageCount] = useState(0);
  const [couponFilters, setCouponFilters] = useState<CouponFilters>(() =>
    createDefaultCouponFilters(),
  );
  const [campaignFilters, setCampaignFilters] = useState<CampaignFilters>(() =>
    createDefaultCampaignFilters(),
  );
  const [packageCampaignFilters, setPackageCampaignFilters] =
    useState<PackageCampaignFilters>(() =>
      createDefaultPackageCampaignFilters(),
    );
  const [referralCampaignFilters, setReferralCampaignFilters] =
    useState<ReferralCampaignFilters>(() =>
      createDefaultReferralCampaignFilters(),
    );
  const campaignPageRef = useRef(campaignPage);
  const campaignFiltersRef = useRef(campaignFilters);
  const packageCampaignPageRef = useRef(packageCampaignPage);
  const packageCampaignFiltersRef = useRef(packageCampaignFilters);
  const referralCampaignPageRef = useRef(referralCampaignPage);
  const referralCampaignFiltersRef = useRef(referralCampaignFilters);
  const [couponCreateOpen, setCouponCreateOpen] = useState(false);
  const [editingCoupon, setEditingCoupon] =
    useState<AdminPromotionCouponItem | null>(null);
  const [campaignCreateOpen, setCampaignCreateOpen] = useState(false);
  const [editingCampaign, setEditingCampaign] = useState<{
    item: AdminPromotionCampaignItem;
    description: string;
  } | null>(null);
  const [packageCampaignCreateOpen, setPackageCampaignCreateOpen] =
    useState(false);
  const [editingPackageCampaign, setEditingPackageCampaign] =
    useState<AdminBillingCampaignDetail | null>(null);
  const [referralCampaignCreateOpen, setReferralCampaignCreateOpen] =
    useState(false);
  const [editingReferralCampaign, setEditingReferralCampaign] =
    useState<AdminReferralCampaignDetail | null>(null);
  const [packageCampaignProductOptions, setPackageCampaignProductOptions] =
    useState<AdminBillingCampaignProductOptions | null>(null);
  const [selectedCouponBid, setSelectedCouponBid] = useState('');
  const [selectedCouponName, setSelectedCouponName] = useState('');
  const [selectedCouponShowCourseColumn, setSelectedCouponShowCourseColumn] =
    useState(false);
  const [couponCodesOpen, setCouponCodesOpen] = useState(false);
  const [selectedPromoBid, setSelectedPromoBid] = useState('');
  const [selectedPromoName, setSelectedPromoName] = useState('');
  const [couponUsageOpen, setCouponUsageOpen] = useState(false);
  const [campaignRedemptionsOpen, setCampaignRedemptionsOpen] = useState(false);
  const [
    packageCampaignProductDetailsOpen,
    setPackageCampaignProductDetailsOpen,
  ] = useState(false);
  const [selectedPackageCampaignBid, setSelectedPackageCampaignBid] =
    useState('');
  const [selectedPackageCampaignName, setSelectedPackageCampaignName] =
    useState('');
  const [pendingStatusChange, setPendingStatusChange] =
    useState<PromotionStatusChangeTarget | null>(null);
  const [statusChangeSubmitting, setStatusChangeSubmitting] = useState(false);
  const [couponFiltersExpanded, setCouponFiltersExpanded] = useState(false);
  const [campaignFiltersExpanded, setCampaignFiltersExpanded] = useState(false);
  const [packageCampaignFiltersExpanded, setPackageCampaignFiltersExpanded] =
    useState(false);
  const [referralCampaignFiltersExpanded, setReferralCampaignFiltersExpanded] =
    useState(false);
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
  const {
    getColumnStyle: getPackageCampaignColumnStyle,
    getResizeHandleProps: getPackageCampaignResizeHandleProps,
  } = useAdminResizableColumns<PackageCampaignColumnKey>({
    storageKey: PACKAGE_CAMPAIGN_COLUMN_WIDTH_STORAGE_KEY,
    defaultWidths: PACKAGE_CAMPAIGN_DEFAULT_COLUMN_WIDTHS,
    minWidth: COLUMN_MIN_WIDTH,
    maxWidth: COLUMN_MAX_WIDTH,
  });
  const {
    getColumnStyle: getReferralCampaignColumnStyle,
    getResizeHandleProps: getReferralCampaignResizeHandleProps,
  } = useAdminResizableColumns<ReferralCampaignColumnKey>({
    storageKey: REFERRAL_CAMPAIGN_COLUMN_WIDTH_STORAGE_KEY,
    defaultWidths: REFERRAL_CAMPAIGN_DEFAULT_COLUMN_WIDTHS,
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

  const renderPackageCampaignResizeHandle = (key: PackageCampaignColumnKey) => (
    <span
      className={ADMIN_TABLE_RESIZE_HANDLE_CLASS}
      {...getPackageCampaignResizeHandleProps(key)}
    />
  );

  const renderReferralCampaignResizeHandle = (
    key: ReferralCampaignColumnKey,
  ) => (
    <span
      className={ADMIN_TABLE_RESIZE_HANDLE_CLASS}
      {...getReferralCampaignResizeHandleProps(key)}
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

  const fetchPackageCampaignProductOptions = useCallback(async () => {
    const response = (await api.getAdminBillingCampaignProductOptions(
      {},
    )) as AdminBillingCampaignProductOptions;
    setPackageCampaignProductOptions(response);
    return response;
  }, []);

  const fetchPackageCampaigns = useCallback(
    async (pageIndex: number, filters: PackageCampaignFilters) => {
      setPackageCampaignLoading(true);
      setPackageCampaignError(null);
      try {
        const requestPayload = {
          page_index: pageIndex,
          page_size: PAGE_SIZE,
          keyword: filters.keyword.trim(),
          product_type: filters.product_type,
          benefit_type: filters.benefit_type,
          status: filters.status,
          start_time: filters.start_time,
          end_time: filters.end_time,
        };
        let response = (await api.getAdminBillingCampaigns(requestPayload)) as {
          items: AdminBillingCampaignItem[];
          page: number;
          page_count: number;
        };
        const responsePage = response.page || pageIndex;
        const responsePageCount = response.page_count || 0;
        if (
          responsePageCount > 0 &&
          responsePage > responsePageCount &&
          (response.items || []).length === 0
        ) {
          response = (await api.getAdminBillingCampaigns({
            ...requestPayload,
            page_index: responsePageCount,
          })) as typeof response;
        }
        setPackageCampaigns(response.items || []);
        setPackageCampaignPage(response.page || 1);
        setPackageCampaignPageCount(response.page_count || 0);
      } catch (error) {
        setPackageCampaignError({
          message:
            (error as Error).message ||
            tPromotion('messages.loadPackageCampaignsFailed'),
        });
        setPackageCampaigns([]);
        setPackageCampaignPage(pageIndex);
        setPackageCampaignPageCount(0);
      } finally {
        setPackageCampaignLoading(false);
      }
    },
    [tPromotion],
  );

  const fetchReferralCampaigns = useCallback(
    async (pageIndex: number, filters: ReferralCampaignFilters) => {
      setReferralCampaignLoading(true);
      setReferralCampaignError(null);
      try {
        const requestPayload = {
          page_index: pageIndex,
          page_size: PAGE_SIZE,
          keyword: filters.keyword.trim(),
          status: filters.status,
          start_time: filters.start_time,
          end_time: filters.end_time,
        };
        let response = (await api.getAdminOperationPromotionReferralCampaigns(
          requestPayload,
        )) as AdminPromotionListResponse<AdminReferralCampaignItem>;
        const responsePage = response.page || pageIndex;
        const responsePageCount = response.page_count || 0;
        if (
          responsePageCount > 0 &&
          responsePage > responsePageCount &&
          (response.items || []).length === 0
        ) {
          response = (await api.getAdminOperationPromotionReferralCampaigns({
            ...requestPayload,
            page_index: responsePageCount,
          })) as AdminPromotionListResponse<AdminReferralCampaignItem>;
        }
        setReferralCampaigns(response.items || []);
        setReferralCampaignPage(response.page || 1);
        setReferralCampaignPageCount(response.page_count || 0);
      } catch (error) {
        setReferralCampaignError({
          message:
            (error as Error).message ||
            tPromotion('messages.loadReferralCampaignsFailed'),
        });
        setReferralCampaigns([]);
        setReferralCampaignPage(pageIndex);
        setReferralCampaignPageCount(0);
      } finally {
        setReferralCampaignLoading(false);
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
  packageCampaignPageRef.current = packageCampaignPage;
  packageCampaignFiltersRef.current = packageCampaignFilters;
  referralCampaignPageRef.current = referralCampaignPage;
  referralCampaignFiltersRef.current = referralCampaignFilters;

  useEffect(() => {
    if (!isReady || tab !== 'campaigns') return;
    // Re-entering the tab should keep the operator on the same filtered page.
    void fetchCampaigns(campaignPageRef.current, campaignFiltersRef.current);
  }, [fetchCampaigns, isReady, tab]);

  useEffect(() => {
    if (!isReady || tab !== 'packageCampaigns') return;
    void fetchPackageCampaigns(
      packageCampaignPageRef.current,
      packageCampaignFiltersRef.current,
    );
  }, [fetchPackageCampaigns, isReady, tab]);

  useEffect(() => {
    if (!isReady || tab !== 'referralCampaigns') return;
    void fetchReferralCampaigns(
      referralCampaignPageRef.current,
      referralCampaignFiltersRef.current,
    );
  }, [fetchReferralCampaigns, isReady, tab]);

  useEffect(() => {
    if (
      !isReady ||
      (tab !== 'packageCampaigns' && tab !== 'referralCampaigns') ||
      packageCampaignProductOptions
    ) {
      return;
    }
    void fetchPackageCampaignProductOptions().catch(error => {
      const nextError = {
        message:
          (error as Error).message ||
          tPromotion('messages.loadPackageCampaignProductsFailed'),
      };
      if (tab === 'referralCampaigns') {
        setReferralCampaignError(nextError);
      } else {
        setPackageCampaignError(nextError);
      }
    });
  }, [
    fetchPackageCampaignProductOptions,
    isReady,
    packageCampaignProductOptions,
    tPromotion,
    tab,
  ]);

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
  const handlePackageCampaignSearch = () =>
    void fetchPackageCampaigns(1, packageCampaignFilters);
  const handlePackageCampaignReset = () => {
    const next = createDefaultPackageCampaignFilters();
    setPackageCampaignFilters(next);
    void fetchPackageCampaigns(1, next);
  };
  const handleReferralCampaignSearch = () =>
    void fetchReferralCampaigns(1, referralCampaignFilters);
  const handleReferralCampaignReset = () => {
    const next = createDefaultReferralCampaignFilters();
    setReferralCampaignFilters(next);
    void fetchReferralCampaigns(1, next);
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

  const handlePackageCampaignCreate = async (
    payload: PackageCampaignFormState,
  ) => {
    const productOptions =
      payload.product_type === 'topup'
        ? packageCampaignProductOptions?.topups || []
        : packageCampaignProductOptions?.plans || [];
    await api.createAdminBillingCampaign({
      name: payload.name.trim(),
      note: payload.note.trim(),
      benefit_type: payload.benefit_type,
      start_at: payload.start_at,
      end_at: payload.end_at,
      products: buildPackageCampaignProductsPayload(payload, productOptions),
    });
    showDefaultToast(tPromotion('messages.createSuccess'));
    await fetchPackageCampaigns(1, packageCampaignFilters);
  };

  const handlePackageCampaignUpdate = async (
    payload: PackageCampaignFormState,
  ) => {
    if (!editingPackageCampaign) {
      return;
    }
    const productOptions =
      payload.product_type === 'topup'
        ? packageCampaignProductOptions?.topups || []
        : packageCampaignProductOptions?.plans || [];
    await api.updateAdminBillingCampaign({
      campaign_bid: editingPackageCampaign.campaign.campaign_bid,
      name: payload.name.trim(),
      note: payload.note.trim(),
      benefit_type: payload.benefit_type,
      start_at: payload.start_at,
      end_at: payload.end_at,
      products: buildPackageCampaignProductsPayload(payload, productOptions),
    });
    showDefaultToast(tPromotion('messages.updateSuccess'));
    await fetchPackageCampaigns(packageCampaignPage, packageCampaignFilters);
    setEditingPackageCampaign(null);
  };

  const handleReferralCampaignCreate = async (
    payload: ReferralCampaignFormState,
  ) => {
    const requestPayload = buildReferralCampaignPayload(payload, {
      includeCampaignCode: true,
    });
    if (!requestPayload) {
      showDefaultToast(tPromotion('validation.referralCampaignJsonInvalid'));
      return;
    }
    await api.createAdminOperationPromotionReferralCampaign(requestPayload);
    showDefaultToast(tPromotion('messages.createSuccess'));
    await fetchReferralCampaigns(1, referralCampaignFilters);
  };

  const handleReferralCampaignUpdate = async (
    payload: ReferralCampaignFormState,
  ) => {
    if (!editingReferralCampaign) {
      return;
    }
    const requestPayload = buildReferralCampaignPayload(payload, {
      includeCampaignCode: false,
    });
    if (!requestPayload) {
      showDefaultToast(tPromotion('validation.referralCampaignJsonInvalid'));
      return;
    }
    await api.updateAdminOperationPromotionReferralCampaign({
      campaign_bid: editingReferralCampaign.campaign.campaign_bid,
      ...requestPayload,
    });
    showDefaultToast(tPromotion('messages.updateSuccess'));
    await fetchReferralCampaigns(referralCampaignPage, referralCampaignFilters);
    setEditingReferralCampaign(null);
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

  const handlePackageCampaignStatusToggle = (
    item: AdminBillingCampaignItem,
  ) => {
    setPendingStatusChange({
      entityType: 'packageCampaign',
      enabling: item.computed_status === 'inactive',
      item,
    });
  };

  const handleReferralCampaignStatusToggle = (
    item: AdminReferralCampaignItem,
  ) => {
    setPendingStatusChange({
      entityType: 'referralCampaign',
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
      } else if (pendingStatusChange.entityType === 'campaign') {
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
      } else if (pendingStatusChange.entityType === 'packageCampaign') {
        await api.updateAdminBillingCampaignStatus({
          campaign_bid: pendingStatusChange.item.campaign_bid,
          enabled: pendingStatusChange.enabling,
        });
        showDefaultToast(
          pendingStatusChange.enabling
            ? tPromotion('messages.packageCampaignEnabledSuccess')
            : tPromotion('messages.packageCampaignDisabledSuccess'),
        );
        await fetchPackageCampaigns(
          packageCampaignPage,
          packageCampaignFilters,
        );
      } else {
        await api.updateAdminOperationPromotionReferralCampaignStatus({
          campaign_bid: pendingStatusChange.item.campaign_bid,
          enabled: pendingStatusChange.enabling,
        });
        showDefaultToast(
          pendingStatusChange.enabling
            ? tPromotion('messages.referralCampaignEnabledSuccess')
            : tPromotion('messages.referralCampaignDisabledSuccess'),
        );
        await fetchReferralCampaigns(
          referralCampaignPage,
          referralCampaignFilters,
        );
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

  const handleStartPackageCampaignEdit = useCallback(
    async (item: AdminBillingCampaignItem) => {
      try {
        if (!packageCampaignProductOptions) {
          await fetchPackageCampaignProductOptions();
        }
        const detail = (await api.getAdminBillingCampaignDetail({
          campaign_bid: item.campaign_bid,
        })) as AdminBillingCampaignDetail;
        setEditingPackageCampaign(detail);
      } catch (error) {
        showErrorToast(
          (error as Error).message ||
            tPromotion('messages.loadPackageCampaignDetailFailed'),
        );
      }
    },
    [
      fetchPackageCampaignProductOptions,
      packageCampaignProductOptions,
      tPromotion,
    ],
  );

  const handleOpenReferralCampaignCreate = useCallback(async () => {
    if (!packageCampaignProductOptions) {
      try {
        await fetchPackageCampaignProductOptions();
      } catch (error) {
        showErrorToast(
          (error as Error).message ||
            tPromotion('messages.loadPackageCampaignProductsFailed'),
        );
        return;
      }
    }
    setReferralCampaignCreateOpen(true);
  }, [
    fetchPackageCampaignProductOptions,
    packageCampaignProductOptions,
    tPromotion,
  ]);

  const handleStartReferralCampaignEdit = useCallback(
    async (item: AdminReferralCampaignItem) => {
      try {
        if (!packageCampaignProductOptions) {
          await fetchPackageCampaignProductOptions();
        }
        const detail =
          (await api.getAdminOperationPromotionReferralCampaignDetail({
            campaign_bid: item.campaign_bid,
          })) as AdminReferralCampaignDetail;
        setEditingReferralCampaign(detail);
      } catch (error) {
        showErrorToast(
          (error as Error).message ||
            tPromotion('messages.loadReferralCampaignDetailFailed'),
        );
      }
    },
    [
      fetchPackageCampaignProductOptions,
      packageCampaignProductOptions,
      tPromotion,
    ],
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
            {COUPON_OPS_STATE_OPTIONS.map(option => (
              <SelectItem
                key={option.value}
                value={option.value}
                className={SINGLE_SELECT_ITEM_CLASS}
              >
                {tPromotion(option.labelKey)}
              </SelectItem>
            ))}
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

  const packageCampaignFilterItems = [
    {
      key: 'keyword',
      label: tPromotion('filters.campaignName'),
      component: (
        <AdminClearableInput
          value={packageCampaignFilters.keyword}
          onChange={value =>
            setPackageCampaignFilters(current => ({
              ...current,
              keyword: value,
            }))
          }
          placeholder={tPromotion('filters.campaignNamePlaceholder')}
          clearLabel={clearLabel}
        />
      ),
    },
    {
      key: 'product_type',
      label: tPromotion('packageCampaign.productType'),
      component: (
        <Select
          value={packageCampaignFilters.product_type || ALL_OPTION_VALUE}
          onValueChange={value =>
            setPackageCampaignFilters(current => ({
              ...current,
              product_type: value === ALL_OPTION_VALUE ? '' : value,
            }))
          }
        >
          <SelectTrigger className='h-9'>
            <SelectValue
              placeholder={tPromotion('packageCampaign.productTypePlaceholder')}
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
              value='plan'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('packageCampaign.productTypePlan')}
            </SelectItem>
            <SelectItem
              value='topup'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('packageCampaign.productTypeTopup')}
            </SelectItem>
          </SelectContent>
        </Select>
      ),
    },
    {
      key: 'benefit_type',
      label: tPromotion('packageCampaign.benefitType'),
      component: (
        <Select
          value={packageCampaignFilters.benefit_type || ALL_OPTION_VALUE}
          onValueChange={value =>
            setPackageCampaignFilters(current => ({
              ...current,
              benefit_type: value === ALL_OPTION_VALUE ? '' : value,
            }))
          }
        >
          <SelectTrigger className='h-9'>
            <SelectValue
              placeholder={tPromotion('packageCampaign.benefitTypePlaceholder')}
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
              value='discount'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('packageCampaign.benefitTypeDiscount')}
            </SelectItem>
            <SelectItem
              value='bonus'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('packageCampaign.benefitTypeBonus')}
            </SelectItem>
          </SelectContent>
        </Select>
      ),
    },
    {
      key: 'status',
      label: tPromotion('filters.status'),
      component: (
        <Select
          value={packageCampaignFilters.status || ALL_OPTION_VALUE}
          onValueChange={value =>
            setPackageCampaignFilters(current => ({
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
              value='upcoming'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('status.upcoming')}
            </SelectItem>
            <SelectItem
              value='active'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('status.active')}
            </SelectItem>
            <SelectItem
              value='inactive'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('status.inactive')}
            </SelectItem>
            <SelectItem
              value='ended'
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('status.ended')}
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
          startValue={packageCampaignFilters.start_time}
          endValue={packageCampaignFilters.end_time}
          onChange={range =>
            setPackageCampaignFilters(current => ({
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

  const referralCampaignFilterItems = [
    {
      key: 'keyword',
      label: tPromotion('filters.campaignName'),
      component: (
        <AdminClearableInput
          value={referralCampaignFilters.keyword}
          onChange={value =>
            setReferralCampaignFilters(current => ({
              ...current,
              keyword: value,
            }))
          }
          placeholder={tPromotion('filters.campaignNamePlaceholder')}
          clearLabel={clearLabel}
        />
      ),
    },
    {
      key: 'status',
      label: tPromotion('filters.status'),
      component: (
        <Select
          value={referralCampaignFilters.status || ALL_OPTION_VALUE}
          onValueChange={value =>
            setReferralCampaignFilters(current => ({
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
      key: 'campaign_time',
      label: tPromotion('filters.campaignTime'),
      component: (
        <AdminDateRangeFilter
          startValue={referralCampaignFilters.start_time}
          endValue={referralCampaignFilters.end_time}
          onChange={range =>
            setReferralCampaignFilters(current => ({
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
              <TabsTrigger value='packageCampaigns'>
                {tPromotion('tabs.packageCampaigns')}
              </TabsTrigger>
              <TabsTrigger value='referralCampaigns'>
                {tPromotion('tabs.referralCampaigns')}
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

        <TabsContent
          value='packageCampaigns'
          className='mt-6 space-y-6'
        >
          <SectionCard
            title=''
            action={
              <Button
                size='sm'
                variant='outline'
                onClick={async () => {
                  if (!packageCampaignProductOptions) {
                    try {
                      await fetchPackageCampaignProductOptions();
                    } catch (error) {
                      showErrorToast(
                        (error as Error).message ||
                          tPromotion(
                            'messages.loadPackageCampaignProductsFailed',
                          ),
                      );
                      return;
                    }
                  }
                  setPackageCampaignCreateOpen(true);
                }}
              >
                <Plus className='mr-1 h-4 w-4' />
                {tPromotion('actions.createPackageCampaign')}
              </Button>
            }
          >
            <AdminFilter
              items={packageCampaignFilterItems}
              expanded={packageCampaignFiltersExpanded}
              onExpandedChange={setPackageCampaignFiltersExpanded}
              onReset={handlePackageCampaignReset}
              onSearch={handlePackageCampaignSearch}
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
          {packageCampaignError ? (
            <ErrorDisplay
              errorMessage={packageCampaignError.message}
              errorCode={0}
            />
          ) : null}
          <AdminTableShell
            loading={packageCampaignLoading}
            isEmpty={!packageCampaigns.length}
            emptyContent={tPromotion('messages.emptyPackageCampaigns')}
            stickyActionEmpty={{
              contentColSpan:
                Object.keys(PACKAGE_CAMPAIGN_DEFAULT_COLUMN_WIDTHS).length - 1,
              actionClassName: TABLE_ACTION_CELL_CLASS,
              actionStyle: getPackageCampaignColumnStyle('action'),
            }}
            withTooltipProvider
            tableWrapperClassName='max-h-[calc(100vh-18rem)] overflow-auto'
            table={emptyRow => (
              <Table containerClassName='overflow-visible max-h-none'>
                <TableHeader>
                  <TableRow>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getPackageCampaignColumnStyle('name')}
                    >
                      {tPromotion('packageCampaign.name')}
                      {renderPackageCampaignResizeHandle('name')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getPackageCampaignColumnStyle('status')}
                    >
                      {tPromotion('table.status')}
                      {renderPackageCampaignResizeHandle('status')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getPackageCampaignColumnStyle('products')}
                    >
                      {tPromotion('packageCampaign.products')}
                      {renderPackageCampaignResizeHandle('products')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getPackageCampaignColumnStyle('rule')}
                    >
                      {tPromotion('packageCampaign.rule')}
                      {renderPackageCampaignResizeHandle('rule')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getPackageCampaignColumnStyle('campaignTime')}
                    >
                      {tPromotion('filters.campaignTime')}
                      {renderPackageCampaignResizeHandle('campaignTime')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getPackageCampaignColumnStyle('benefitType')}
                    >
                      {tPromotion('packageCampaign.benefitType')}
                      {renderPackageCampaignResizeHandle('benefitType')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getPackageCampaignColumnStyle('productType')}
                    >
                      {tPromotion('packageCampaign.productType')}
                      {renderPackageCampaignResizeHandle('productType')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getPackageCampaignColumnStyle('hitOrderCount')}
                    >
                      {tPromotion('packageCampaign.hitOrderCount')}
                      {renderPackageCampaignResizeHandle('hitOrderCount')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getPackageCampaignColumnStyle('updatedAt')}
                    >
                      {tPromotion('table.updatedAt')}
                      {renderPackageCampaignResizeHandle('updatedAt')}
                    </TableHead>
                    <TableHead
                      className={TABLE_ACTION_HEAD_CLASS}
                      style={getPackageCampaignColumnStyle('action')}
                    >
                      {tPromotion('table.actions')}
                      {renderPackageCampaignResizeHandle('action')}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {emptyRow}
                  {packageCampaigns.map(item => (
                    <TableRow key={item.campaign_bid}>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getPackageCampaignColumnStyle('name')}
                      >
                        {renderTooltipText(item.name)}
                      </TableCell>
                      <TableCell
                        className={cn(TABLE_CELL_CLASS, 'whitespace-normal')}
                        style={getPackageCampaignColumnStyle('status')}
                      >
                        <div className='flex flex-wrap items-center justify-center gap-1'>
                          {renderPromotionStatusBadge({
                            tPromotion,
                            status: item.computed_status,
                          })}
                        </div>
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getPackageCampaignColumnStyle('products')}
                      >
                        <Button
                          type='button'
                          variant='link'
                          className='h-auto max-w-full justify-start p-0 text-left font-normal'
                          onClick={() => {
                            setSelectedPackageCampaignBid(item.campaign_bid);
                            setSelectedPackageCampaignName(
                              item.name || item.campaign_bid,
                            );
                            setPackageCampaignProductDetailsOpen(true);
                          }}
                        >
                          {renderTooltipText(
                            resolvePackageCampaignProductSummary(
                              tPromotion,
                              item,
                            ),
                          )}
                        </Button>
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getPackageCampaignColumnStyle('rule')}
                      >
                        {renderTooltipText(
                          resolvePackageCampaignRuleLabel(t, item),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getPackageCampaignColumnStyle('campaignTime')}
                      >
                        {renderTooltipText(
                          renderTimeRange(item.start_at, item.end_at),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getPackageCampaignColumnStyle('benefitType')}
                      >
                        {renderTooltipText(
                          resolvePackageCampaignBenefitTypeLabel(
                            tPromotion,
                            item.benefit_type,
                          ),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getPackageCampaignColumnStyle('productType')}
                      >
                        {renderTooltipText(
                          resolvePackageCampaignProductTypeLabel(
                            tPromotion,
                            item.product_types[0],
                          ),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getPackageCampaignColumnStyle('hitOrderCount')}
                      >
                        {renderTooltipText(String(item.hit_order_count || 0))}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getPackageCampaignColumnStyle('updatedAt')}
                      >
                        {renderTooltipText(
                          formatAdminUtcDateTime(item.updated_at),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_ACTION_CELL_CLASS}
                        style={getPackageCampaignColumnStyle('action')}
                      >
                        <div className='flex justify-center'>
                          <AdminRowActions
                            label={t('common.core.more')}
                            actions={[
                              {
                                key: 'edit',
                                label: tPromotion('actions.edit'),
                                onClick: () =>
                                  void handleStartPackageCampaignEdit(item),
                              },
                              {
                                key: 'toggle-status',
                                label:
                                  item.computed_status === 'inactive'
                                    ? tPromotion('actions.enable')
                                    : tPromotion('actions.disable'),
                                hidden:
                                  !shouldShowPackageCampaignStatusToggle(item),
                                onClick: () =>
                                  void handlePackageCampaignStatusToggle(item),
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
              pageIndex: packageCampaignPage,
              pageCount: packageCampaignPageCount,
              onPageChange: page =>
                void fetchPackageCampaigns(page, packageCampaignFilters),
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
          value='referralCampaigns'
          className='mt-6 space-y-6'
        >
          <ReferralCampaignsTab
            t={t}
            tPromotion={tPromotion}
            filterItems={referralCampaignFilterItems}
            filtersExpanded={referralCampaignFiltersExpanded}
            onFiltersExpandedChange={setReferralCampaignFiltersExpanded}
            onReset={handleReferralCampaignReset}
            onSearch={handleReferralCampaignSearch}
            onCreate={() => void handleOpenReferralCampaignCreate()}
            error={referralCampaignError}
            loading={referralCampaignLoading}
            campaigns={referralCampaigns}
            page={referralCampaignPage}
            pageCount={referralCampaignPageCount}
            filters={referralCampaignFilters}
            fetchCampaigns={fetchReferralCampaigns}
            productOptions={packageCampaignProductOptions}
            getColumnStyle={getReferralCampaignColumnStyle}
            renderResizeHandle={renderReferralCampaignResizeHandle}
            onEdit={handleStartReferralCampaignEdit}
            onToggleStatus={handleReferralCampaignStatusToggle}
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
      <PackageCampaignDialog
        open={packageCampaignCreateOpen}
        onOpenChange={setPackageCampaignCreateOpen}
        onSubmit={handlePackageCampaignCreate}
        productOptions={packageCampaignProductOptions}
      />
      <PackageCampaignDialog
        open={Boolean(editingPackageCampaign)}
        onOpenChange={open => {
          if (!open) {
            setEditingPackageCampaign(null);
          }
        }}
        onSubmit={handlePackageCampaignUpdate}
        campaign={editingPackageCampaign}
        productOptions={packageCampaignProductOptions}
      />
      <ReferralCampaignDialog
        open={referralCampaignCreateOpen}
        onOpenChange={setReferralCampaignCreateOpen}
        onSubmit={handleReferralCampaignCreate}
        productOptions={packageCampaignProductOptions}
      />
      <ReferralCampaignDialog
        open={Boolean(editingReferralCampaign)}
        onOpenChange={open => {
          if (!open) {
            setEditingReferralCampaign(null);
          }
        }}
        onSubmit={handleReferralCampaignUpdate}
        campaign={editingReferralCampaign}
        productOptions={packageCampaignProductOptions}
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
      <PackageCampaignProductDetailsDialog
        open={packageCampaignProductDetailsOpen}
        onOpenChange={open => {
          setPackageCampaignProductDetailsOpen(open);
          if (!open) {
            setSelectedPackageCampaignBid('');
            setSelectedPackageCampaignName('');
          }
        }}
        campaignBid={selectedPackageCampaignBid}
        campaignName={selectedPackageCampaignName}
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
