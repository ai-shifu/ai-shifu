import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminClearableInput from '@/app/admin/components/AdminClearableInput';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import type {
  AdminPromotionCampaignRedemptionItem,
  AdminPromotionCouponCodeItem,
  AdminPromotionCouponUsageItem,
  AdminPromotionListResponse,
} from '@/app/admin/operations/operation-promotion-types';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { showErrorToast } from '@/hooks/useToast';
import {
  EMPTY_VALUE,
  PAGE_SIZE,
  PROMOTION_CODE_DIALOG_COLUMN_COUNT,
  PROMOTION_REDEMPTION_DIALOG_COLUMN_COUNT,
  PROMOTION_USAGE_DIALOG_COLUMN_COUNT,
  renderTooltipText,
  renderUserLabel,
  TABLE_CELL_CLASS,
  TABLE_HEAD_CLASS,
  TABLE_LAST_CELL_CLASS,
} from './promotionPageShared';

export const PromotionCouponCodesDialog = ({
  open,
  onOpenChange,
  couponBid,
  couponName,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  couponBid: string;
  couponName: string;
}) => {
  const { t } = useTranslation();
  const { t: tPromotion } = useTranslation('module.operationsPromotion');
  const [loading, setLoading] = useState(false);
  const [pageIndex, setPageIndex] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [codes, setCodes] = useState<AdminPromotionCouponCodeItem[]>([]);
  const [keyword, setKeyword] = useState('');
  const [appliedKeyword, setAppliedKeyword] = useState('');

  const fetchCodes = useCallback(
    async (nextPage: number, nextKeyword: string) => {
      if (!couponBid) {
        return;
      }
      setLoading(true);
      try {
        const response = (await api.getAdminOperationPromotionCouponCodes({
          coupon_bid: couponBid,
          page_index: nextPage,
          page_size: PAGE_SIZE,
          keyword: nextKeyword,
        })) as AdminPromotionListResponse<AdminPromotionCouponCodeItem>;
        setCodes(response.items || []);
        setPageIndex(response.page || nextPage);
        setPageCount(response.page_count || 0);
      } catch (error) {
        setCodes([]);
        setPageIndex(nextPage);
        setPageCount(0);
        showErrorToast(
          (error as Error).message || tPromotion('messages.loadCodesFailed'),
        );
      } finally {
        setLoading(false);
      }
    },
    [couponBid, tPromotion],
  );

  useEffect(() => {
    if (!open || !couponBid) {
      return;
    }
    setKeyword(current => (current ? '' : current));
    setAppliedKeyword(current => (current ? '' : current));
    void fetchCodes(1, '');
  }, [couponBid, fetchCodes, open]);

  const handleSearch = () => {
    const nextKeyword = keyword.trim();
    setAppliedKeyword(nextKeyword);
    void fetchCodes(1, nextKeyword);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className='sm:max-w-4xl'>
        <DialogHeader>
          <DialogTitle>{tPromotion('coupon.codes')}</DialogTitle>
        </DialogHeader>
        <div className='flex max-h-[70vh] min-h-0 flex-col overflow-hidden'>
          <div className='mb-4 text-sm text-muted-foreground'>
            {couponName || couponBid}
          </div>
          <div className='mb-4 flex items-center gap-3'>
            <div className='w-full max-w-sm'>
              <AdminClearableInput
                value={keyword}
                onChange={setKeyword}
                placeholder={tPromotion('coupon.subCodePlaceholder')}
                clearLabel={t('common.core.close')}
              />
            </div>
            <Button
              type='button'
              size='sm'
              onClick={handleSearch}
            >
              {tPromotion('actions.search')}
            </Button>
          </div>
          <AdminTableShell
            loading={loading}
            isEmpty={codes.length === 0}
            emptyContent={tPromotion('messages.emptyCodes')}
            emptyColSpan={PROMOTION_CODE_DIALOG_COLUMN_COUNT}
            withTooltipProvider
            containerClassName='min-h-0 flex-1'
            tableWrapperClassName='min-h-0 flex-1 overflow-auto'
            table={emptyRow => (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('coupon.subCode')}
                    </TableHead>
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('table.status')}
                    </TableHead>
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('table.user')}
                    </TableHead>
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('table.orderBid')}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {emptyRow}
                  {codes.map(item => (
                    <TableRow key={item.coupon_usage_bid}>
                      <TableCell className={TABLE_CELL_CLASS}>
                        {renderTooltipText(item.code)}
                      </TableCell>
                      <TableCell className={TABLE_CELL_CLASS}>
                        {renderTooltipText(
                          item.status_key ? t(item.status_key) : EMPTY_VALUE,
                        )}
                      </TableCell>
                      <TableCell className={TABLE_CELL_CLASS}>
                        {renderTooltipText(renderUserLabel(item))}
                      </TableCell>
                      <TableCell className={TABLE_LAST_CELL_CLASS}>
                        {renderTooltipText(item.order_bid)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            pagination={{
              pageIndex,
              pageCount,
              onPageChange: page => void fetchCodes(page, appliedKeyword),
              prevLabel: t('module.order.paginationPrev'),
              nextLabel: t('module.order.paginationNext'),
              prevAriaLabel: t('module.order.paginationPrevAriaLabel'),
              nextAriaLabel: t('module.order.paginationNextAriaLabel'),
              hideWhenSinglePage: true,
            }}
            footerClassName='mt-3'
          />
        </div>
      </DialogContent>
    </Dialog>
  );
};

export const PromotionCampaignRedemptionsDialog = ({
  open,
  onOpenChange,
  promoBid,
  campaignName,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  promoBid: string;
  campaignName: string;
}) => {
  const { t } = useTranslation();
  const { t: tPromotion } = useTranslation('module.operationsPromotion');
  const [loading, setLoading] = useState(false);
  const [pageIndex, setPageIndex] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [redemptions, setRedemptions] = useState<
    AdminPromotionCampaignRedemptionItem[]
  >([]);

  const fetchRedemptions = useCallback(
    async (nextPage: number) => {
      if (!promoBid) {
        return;
      }
      setLoading(true);
      try {
        const response =
          (await api.getAdminOperationPromotionCampaignRedemptions({
            promo_bid: promoBid,
            page_index: nextPage,
            page_size: PAGE_SIZE,
          })) as AdminPromotionListResponse<AdminPromotionCampaignRedemptionItem>;
        setRedemptions(response.items || []);
        setPageIndex(response.page || nextPage);
        setPageCount(response.page_count || 0);
      } catch (error) {
        setRedemptions([]);
        setPageIndex(nextPage);
        setPageCount(0);
        showErrorToast(
          (error as Error).message ||
            tPromotion('messages.loadRedemptionsFailed'),
        );
      } finally {
        setLoading(false);
      }
    },
    [promoBid, tPromotion],
  );

  useEffect(() => {
    if (!open || !promoBid) {
      return;
    }
    void fetchRedemptions(1);
  }, [fetchRedemptions, open, promoBid]);

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className='sm:max-w-5xl'>
        <DialogHeader>
          <DialogTitle>{tPromotion('campaign.redemptions')}</DialogTitle>
        </DialogHeader>
        <div className='flex max-h-[70vh] min-h-0 flex-col overflow-hidden'>
          <div className='mb-4 text-sm text-muted-foreground'>
            {campaignName || promoBid}
          </div>
          <AdminTableShell
            loading={loading}
            isEmpty={redemptions.length === 0}
            emptyContent={tPromotion('messages.emptyRedemptions')}
            emptyColSpan={PROMOTION_REDEMPTION_DIALOG_COLUMN_COUNT}
            withTooltipProvider
            containerClassName='min-h-0 flex-1'
            tableWrapperClassName='min-h-0 flex-1 overflow-auto'
            table={emptyRow => (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('table.appliedAt')}
                    </TableHead>
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('table.user')}
                    </TableHead>
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('table.orderBid')}
                    </TableHead>
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('campaign.discountAmount')}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {emptyRow}
                  {redemptions.map(item => (
                    <TableRow key={item.redemption_bid}>
                      <TableCell className={TABLE_CELL_CLASS}>
                        {renderTooltipText(
                          formatAdminUtcDateTime(item.applied_at),
                        )}
                      </TableCell>
                      <TableCell className={TABLE_CELL_CLASS}>
                        {renderTooltipText(renderUserLabel(item))}
                      </TableCell>
                      <TableCell className={TABLE_CELL_CLASS}>
                        {renderTooltipText(item.order_bid)}
                      </TableCell>
                      <TableCell className={TABLE_LAST_CELL_CLASS}>
                        {renderTooltipText(item.discount_amount)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            pagination={{
              pageIndex,
              pageCount,
              onPageChange: page => void fetchRedemptions(page),
              prevLabel: t('module.order.paginationPrev'),
              nextLabel: t('module.order.paginationNext'),
              prevAriaLabel: t('module.order.paginationPrevAriaLabel'),
              nextAriaLabel: t('module.order.paginationNextAriaLabel'),
              hideWhenSinglePage: true,
            }}
            footerClassName='mt-3'
          />
        </div>
      </DialogContent>
    </Dialog>
  );
};

export const PromotionCouponUsageDialog = ({
  open,
  onOpenChange,
  couponBid,
  couponName,
  showCourseColumn,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  couponBid: string;
  couponName: string;
  showCourseColumn: boolean;
}) => {
  const { t } = useTranslation();
  const { t: tPromotion } = useTranslation('module.operationsPromotion');
  const [loading, setLoading] = useState(false);
  const [pageIndex, setPageIndex] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [usages, setUsages] = useState<AdminPromotionCouponUsageItem[]>([]);

  const fetchUsages = useCallback(
    async (nextPage: number) => {
      if (!couponBid) {
        return;
      }
      setLoading(true);
      try {
        const response = (await api.getAdminOperationPromotionCouponUsages({
          coupon_bid: couponBid,
          page_index: nextPage,
          page_size: PAGE_SIZE,
        })) as AdminPromotionListResponse<AdminPromotionCouponUsageItem>;
        setUsages(response.items || []);
        setPageIndex(response.page || nextPage);
        setPageCount(response.page_count || 0);
      } catch (error) {
        setUsages([]);
        setPageIndex(nextPage);
        setPageCount(0);
        showErrorToast(
          (error as Error).message || tPromotion('messages.loadUsagesFailed'),
        );
      } finally {
        setLoading(false);
      }
    },
    [couponBid, tPromotion],
  );

  useEffect(() => {
    if (!open || !couponBid) {
      return;
    }
    void fetchUsages(1);
  }, [couponBid, fetchUsages, open]);

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className='sm:max-w-4xl'>
        <DialogHeader>
          <DialogTitle>{tPromotion('coupon.usages')}</DialogTitle>
        </DialogHeader>
        <div className='flex max-h-[70vh] min-h-0 flex-col overflow-hidden'>
          <div className='mb-4 text-sm text-muted-foreground'>
            {couponName || couponBid}
          </div>
          <AdminTableShell
            loading={loading}
            isEmpty={usages.length === 0}
            emptyContent={tPromotion('messages.emptyUsages')}
            emptyColSpan={
              showCourseColumn
                ? PROMOTION_USAGE_DIALOG_COLUMN_COUNT.withCourse
                : PROMOTION_USAGE_DIALOG_COLUMN_COUNT.default
            }
            withTooltipProvider
            containerClassName='min-h-0 flex-1'
            tableWrapperClassName='min-h-0 flex-1 overflow-auto'
            table={emptyRow => (
              <Table containerClassName='overflow-visible max-h-none'>
                <TableHeader>
                  <TableRow>
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('table.usedAt')}
                    </TableHead>
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('coupon.code')}
                    </TableHead>
                    {showCourseColumn ? (
                      <TableHead className={TABLE_HEAD_CLASS}>
                        {tPromotion('table.redeemedCourse')}
                      </TableHead>
                    ) : null}
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('table.user')}
                    </TableHead>
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('table.orderBid')}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {emptyRow}
                  {usages.map(item => (
                    <TableRow key={item.coupon_usage_bid}>
                      <TableCell className={TABLE_CELL_CLASS}>
                        {renderTooltipText(
                          formatAdminUtcDateTime(item.used_at),
                        )}
                      </TableCell>
                      <TableCell className={TABLE_CELL_CLASS}>
                        {renderTooltipText(item.code)}
                      </TableCell>
                      {showCourseColumn ? (
                        <TableCell className={TABLE_CELL_CLASS}>
                          {renderTooltipText(
                            item.course_name || item.shifu_bid || EMPTY_VALUE,
                          )}
                        </TableCell>
                      ) : null}
                      <TableCell className={TABLE_CELL_CLASS}>
                        {renderTooltipText(renderUserLabel(item))}
                      </TableCell>
                      <TableCell className={TABLE_LAST_CELL_CLASS}>
                        {renderTooltipText(item.order_bid)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            pagination={{
              pageIndex,
              pageCount,
              onPageChange: page => void fetchUsages(page),
              prevLabel: t('module.order.paginationPrev'),
              nextLabel: t('module.order.paginationNext'),
              prevAriaLabel: t('module.order.paginationPrevAriaLabel'),
              nextAriaLabel: t('module.order.paginationNextAriaLabel'),
              hideWhenSinglePage: true,
            }}
            footerClassName='mt-3'
          />
        </div>
      </DialogContent>
    </Dialog>
  );
};
