'use client';

import React, { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import type {
  AdminPromotionCouponDetail,
  AdminPromotionCouponCodeItem,
  AdminPromotionCouponItem,
  AdminPromotionCouponUsageItem,
  AdminPromotionListResponse,
} from '@/app/admin/operations/operation-promotion-types';
import {
  PromotionCouponCodesDialog,
  PromotionCouponUsageDialog,
} from '@/app/admin/operations/promotions/PromotionRecordDialogs';
import { downloadExcelCompatibleCodesFile } from '@/app/admin/operations/promotions/promotionPageShared';
import PromotionStatusConfirmDialog from '@/app/admin/operations/promotions/PromotionStatusConfirmDialog';
import ErrorDisplay from '@/components/ErrorDisplay';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';
import { showDefaultToast, showErrorToast } from '@/hooks/useToast';
import CreatorRedemptionCodeDialog from './CreatorRedemptionCodeDialog';
import CreatorRedemptionCodesFilterPanel from './CreatorRedemptionCodesFilterPanel';
import CreatorRedemptionCodesTable from './CreatorRedemptionCodesTable';
import { useCreatorRedemptionCodesList } from './useCreatorRedemptionCodesList';

export default function CreatorRedemptionCodesTab({
  reloadKey = 0,
}: {
  reloadKey?: number;
}) {
  const { t } = useTranslation();
  const { t: tPromotion } = useTranslation('module.operationsPromotion');
  const currencySymbol = useEnvStore(
    (state: EnvStoreState) => state.currencySymbol,
  );
  const [usageDialogOpen, setUsageDialogOpen] = useState(false);
  const [codesDialogOpen, setCodesDialogOpen] = useState(false);
  const [selectedCouponBid, setSelectedCouponBid] = useState('');
  const [selectedCouponName, setSelectedCouponName] = useState('');
  const [editingCoupon, setEditingCoupon] =
    useState<AdminPromotionCouponItem | null>(null);
  const [statusTarget, setStatusTarget] =
    useState<AdminPromotionCouponItem | null>(null);
  const [statusSubmitting, setStatusSubmitting] = useState(false);
  const {
    error,
    expanded,
    fetchCodes,
    filters,
    filtersRef,
    handleFilterChange,
    handlePageChange,
    handleReset,
    handleSearch,
    items,
    loading,
    pageCount,
    pageIndex,
    setExpanded,
    total,
  } = useCreatorRedemptionCodesList({
    reloadKey,
    t,
  });

  const handleOpenUsage = (item: AdminPromotionCouponItem) => {
    setSelectedCouponBid(item.coupon_bid);
    setSelectedCouponName(item.name);
    setUsageDialogOpen(true);
  };

  const handleOpenCodes = (item: AdminPromotionCouponItem) => {
    setSelectedCouponBid(item.coupon_bid);
    setSelectedCouponName(item.name);
    setCodesDialogOpen(true);
  };

  const handleStartEdit = async (item: AdminPromotionCouponItem) => {
    try {
      const detail = (await api.getCreatorCourseRedemptionCodeDetail({
        coupon_bid: item.coupon_bid,
      })) as AdminPromotionCouponDetail;
      setEditingCoupon(detail.coupon || item);
    } catch (err) {
      showErrorToast(
        (err as Error).message || tPromotion('messages.loadCouponDetailFailed'),
      );
    }
  };

  const handleStatusToggle = (item: AdminPromotionCouponItem) => {
    setStatusTarget(item);
  };

  const handleConfirmStatusToggle = async () => {
    if (!statusTarget) {
      return;
    }
    const enabling = statusTarget.computed_status === 'inactive';
    setStatusSubmitting(true);
    try {
      await api.updateCreatorCourseRedemptionCodeStatus({
        coupon_bid: statusTarget.coupon_bid,
        enabled: enabling,
      });
      showDefaultToast(
        enabling
          ? tPromotion('messages.couponEnabledSuccess')
          : tPromotion('messages.couponDisabledSuccess'),
      );
      setStatusTarget(current => (current ? null : current));
      await fetchCodes(pageIndex, filtersRef.current);
    } catch (err) {
      showErrorToast((err as Error).message || t('common.core.submitFailed'));
    } finally {
      setStatusSubmitting(false);
    }
  };

  const fetchCreatorUsages = useCallback(
    (params: { coupon_bid: string; page_index: number; page_size: number }) =>
      api.getCreatorCourseRedemptionCodeUsages(params) as Promise<
        AdminPromotionListResponse<AdminPromotionCouponUsageItem>
      >,
    [],
  );

  const fetchCreatorSubCodes = useCallback(
    (params: {
      coupon_bid: string;
      page_index: number;
      page_size: number;
      keyword?: string;
    }) =>
      api.getCreatorCourseRedemptionCodeCodes(params) as Promise<
        AdminPromotionListResponse<AdminPromotionCouponCodeItem>
      >,
    [],
  );

  const handleExportCodes = async (item: AdminPromotionCouponItem) => {
    if (Number(item.usage_type) !== 802) {
      return;
    }

    try {
      const allCodes: string[] = [];
      let nextPage = 1;
      let nextPageCount = 1;

      while (nextPage <= nextPageCount) {
        const response = await fetchCreatorSubCodes({
          coupon_bid: item.coupon_bid,
          page_index: nextPage,
          page_size: 100,
        });
        (response.items || []).forEach(codeItem => {
          if (codeItem.code) {
            allCodes.push(codeItem.code);
          }
        });
        nextPageCount = response.page_count || 0;
        nextPage += 1;
      }

      if (!allCodes.length) {
        showDefaultToast(tPromotion('messages.emptyCodes'));
        return;
      }

      const safeBaseName = (item.name || item.coupon_bid || 'coupon-codes')
        .trim()
        .replace(/[\\/:*?"<>|]+/g, '-');
      downloadExcelCompatibleCodesFile(
        `${safeBaseName}.xls`,
        tPromotion('coupon.code'),
        allCodes,
      );
      showDefaultToast(tPromotion('messages.exportSuccess'));
    } catch (err) {
      showErrorToast(
        (err as Error).message || tPromotion('messages.exportFailed'),
      );
    }
  };

  return (
    <div className='flex h-full min-h-0 flex-col gap-5 pb-6'>
      <CreatorRedemptionCodesFilterPanel
        expanded={expanded}
        filters={filters}
        onExpandedChange={setExpanded}
        onFilterChange={handleFilterChange}
        onReset={handleReset}
        onSearch={handleSearch}
        t={t}
        tPromotion={tPromotion}
      />

      {error ? (
        <ErrorDisplay
          errorMessage={error.message}
          errorCode={0}
        />
      ) : null}

      <CreatorRedemptionCodesTable
        currencySymbol={currencySymbol || ''}
        hasError={Boolean(error)}
        items={items}
        loading={loading}
        onEdit={item => void handleStartEdit(item)}
        onExportCodes={item => void handleExportCodes(item)}
        onOpenCodes={handleOpenCodes}
        onOpenUsage={handleOpenUsage}
        onPageChange={handlePageChange}
        onToggleStatus={handleStatusToggle}
        pageCount={pageCount}
        pageIndex={pageIndex}
        t={t}
        tPromotion={tPromotion}
        total={total}
      />
      <PromotionCouponUsageDialog
        open={usageDialogOpen}
        onOpenChange={setUsageDialogOpen}
        couponBid={selectedCouponBid}
        couponName={selectedCouponName}
        showCourseColumn={false}
        fetchUsagesApi={fetchCreatorUsages}
      />
      <PromotionCouponCodesDialog
        open={codesDialogOpen}
        onOpenChange={setCodesDialogOpen}
        couponBid={selectedCouponBid}
        couponName={selectedCouponName}
        fetchCodesApi={fetchCreatorSubCodes}
      />
      <CreatorRedemptionCodeDialog
        open={Boolean(editingCoupon)}
        onOpenChange={open => {
          if (!open) {
            setEditingCoupon(current => (current ? null : current));
          }
        }}
        coupon={editingCoupon}
        onSuccess={() => fetchCodes(pageIndex, filtersRef.current)}
      />
      <PromotionStatusConfirmDialog
        changeTarget={
          statusTarget
            ? {
                entityType: 'coupon',
                enabling: statusTarget.computed_status === 'inactive',
                item: statusTarget,
              }
            : null
        }
        submitting={statusSubmitting}
        onOpenChange={open => {
          if (!open && !statusSubmitting) {
            setStatusTarget(current => (current ? null : current));
          }
        }}
        onConfirm={handleConfirmStatusToggle}
      />
    </div>
  );
}
