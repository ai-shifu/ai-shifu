import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminClearableInput from '@/app/admin/components/AdminClearableInput';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import type {
  AdminBillingCampaignDetail,
  AdminBillingCampaignProductOption,
  AdminPromotionCampaignRedemptionItem,
  AdminPromotionCouponCodeItem,
  AdminPromotionCouponUsageItem,
  AdminPromotionListResponse,
} from '@/app/admin/operations/operation-promotion-types';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { formatBillingCreditAmount, formatBillingPrice } from '@/lib/billing';
import {
  EMPTY_VALUE,
  PACKAGE_CAMPAIGN_PRODUCT_DIALOG_COLUMN_COUNT,
  PAGE_SIZE,
  PROMOTION_CODE_DIALOG_COLUMN_COUNT,
  PROMOTION_REDEMPTION_DIALOG_COLUMN_COUNT,
  PROMOTION_USAGE_DIALOG_COLUMN_COUNT,
  renderTooltipText,
  renderUserLabel,
  resolvePackageCampaignOptionTitle,
  resolvePackageCampaignProductTypeLabel,
  TABLE_CELL_CLASS,
  TABLE_HEAD_CLASS,
  TABLE_LAST_CELL_CLASS,
} from './promotionPageShared';

type CouponUsageFetchParams = {
  coupon_bid: string;
  page_index: number;
  page_size: number;
};

type CouponUsageFetch = (
  params: CouponUsageFetchParams,
) => Promise<AdminPromotionListResponse<AdminPromotionCouponUsageItem>>;

type CouponCodesFetchParams = CouponUsageFetchParams & {
  keyword?: string;
};

type CouponCodesFetch = (
  params: CouponCodesFetchParams,
) => Promise<AdminPromotionListResponse<AdminPromotionCouponCodeItem>>;

type PackageCampaignDetailFetch = (params: {
  campaign_bid: string;
}) => Promise<AdminBillingCampaignDetail>;

const resolvePackageCampaignProductBenefitLabel = (
  tPromotion: (key: string, options?: Record<string, unknown>) => string,
  product: AdminBillingCampaignProductOption,
  locale: string,
) => {
  if (product.campaign_bonus_credit_amount > 0) {
    return tPromotion('packageCampaign.ruleBonus', {
      value: formatBillingCreditAmount(product.campaign_bonus_credit_amount),
    });
  }
  if (product.campaign_discount_type === 'percent') {
    return tPromotion('packageCampaign.productDetailsPercent', {
      value: product.campaign_discount_percent,
      price: formatBillingPrice(
        product.campaign_price_amount,
        product.currency,
        locale,
      ),
    });
  }
  if (product.campaign_price_amount > 0) {
    return tPromotion('packageCampaign.productDetailsCampaignPrice', {
      value: formatBillingPrice(
        product.campaign_price_amount,
        product.currency,
        locale,
      ),
    });
  }
  if (product.campaign_discount_amount > 0) {
    return tPromotion('packageCampaign.productDetailsDiscountAmount', {
      value: formatBillingPrice(
        product.campaign_discount_amount,
        product.currency,
        locale,
      ),
    });
  }
  return EMPTY_VALUE;
};

export const PackageCampaignProductDetailsDialog = ({
  open,
  onOpenChange,
  campaignBid,
  campaignName,
  fetchDetailApi = api.getAdminBillingCampaignDetail as PackageCampaignDetailFetch,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  campaignBid: string;
  campaignName: string;
  fetchDetailApi?: PackageCampaignDetailFetch;
}) => {
  const { t, i18n } = useTranslation();
  const { t: tPromotion } = useTranslation('module.operationsPromotion');
  const [loading, setLoading] = useState(false);
  const [products, setProducts] = useState<AdminBillingCampaignProductOption[]>(
    [],
  );
  const detailRequestIdRef = useRef(0);

  const fetchDetail = useCallback(async () => {
    if (!campaignBid) {
      return;
    }
    const requestId = ++detailRequestIdRef.current;
    setLoading(true);
    try {
      const detail = await fetchDetailApi({ campaign_bid: campaignBid });
      if (requestId !== detailRequestIdRef.current) return;
      setProducts(detail.products || []);
    } catch (error) {
      if (requestId !== detailRequestIdRef.current) return;
      setProducts([]);
      showErrorToast(
        (error as Error).message ||
          tPromotion('messages.loadPackageCampaignDetailFailed'),
      );
    } finally {
      if (requestId === detailRequestIdRef.current) {
        setLoading(false);
      }
    }
  }, [campaignBid, fetchDetailApi, tPromotion]);

  useEffect(() => {
    if (!open || !campaignBid) {
      return;
    }
    void fetchDetail();
  }, [campaignBid, fetchDetail, open]);

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className='sm:max-w-4xl'>
        <DialogHeader>
          <DialogTitle>
            {tPromotion('packageCampaign.productDetails')}
          </DialogTitle>
          <DialogDescription className='sr-only'>
            {campaignName || campaignBid}
          </DialogDescription>
        </DialogHeader>
        <div className='flex max-h-[70vh] min-h-0 flex-col overflow-hidden'>
          <div className='mb-4 text-sm text-muted-foreground'>
            {campaignName || campaignBid}
          </div>
          <AdminTableShell
            loading={loading}
            isEmpty={products.length === 0}
            emptyContent={tPromotion('packageCampaign.productsUnavailable')}
            emptyColSpan={PACKAGE_CAMPAIGN_PRODUCT_DIALOG_COLUMN_COUNT}
            withTooltipProvider
            containerClassName='min-h-0 flex-1'
            tableWrapperClassName='min-h-0 flex-1 overflow-auto'
            table={emptyRow => (
              <Table className='table-fixed'>
                <TableHeader>
                  <TableRow>
                    <TableHead className={`${TABLE_HEAD_CLASS} w-[260px]`}>
                      {tPromotion('packageCampaign.productName')}
                    </TableHead>
                    <TableHead className={`${TABLE_HEAD_CLASS} w-[96px]`}>
                      {tPromotion('packageCampaign.productType')}
                    </TableHead>
                    <TableHead className={`${TABLE_HEAD_CLASS} w-[120px]`}>
                      {tPromotion('packageCampaign.originalPrice')}
                    </TableHead>
                    <TableHead className={`${TABLE_HEAD_CLASS} w-[96px]`}>
                      {tPromotion('packageCampaign.originalCredits')}
                    </TableHead>
                    <TableHead className={`${TABLE_HEAD_CLASS} w-[220px]`}>
                      {tPromotion('packageCampaign.productBenefit')}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {emptyRow}
                  {products.map(product => (
                    <TableRow key={product.product_bid}>
                      <TableCell className={TABLE_CELL_CLASS}>
                        {renderTooltipText(
                          resolvePackageCampaignOptionTitle(t, product),
                        )}
                      </TableCell>
                      <TableCell className={TABLE_CELL_CLASS}>
                        {renderTooltipText(
                          resolvePackageCampaignProductTypeLabel(
                            tPromotion,
                            product.product_type,
                          ),
                        )}
                      </TableCell>
                      <TableCell className={TABLE_CELL_CLASS}>
                        {renderTooltipText(
                          formatBillingPrice(
                            product.price_amount,
                            product.currency,
                            i18n.language,
                          ),
                        )}
                      </TableCell>
                      <TableCell className={TABLE_CELL_CLASS}>
                        {renderTooltipText(
                          formatBillingCreditAmount(product.credit_amount),
                        )}
                      </TableCell>
                      <TableCell className={TABLE_LAST_CELL_CLASS}>
                        {renderTooltipText(
                          resolvePackageCampaignProductBenefitLabel(
                            tPromotion,
                            product,
                            i18n.language,
                          ),
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
};

export const PromotionCouponCodesDialog = ({
  open,
  onOpenChange,
  couponBid,
  couponName,
  fetchCodesApi = api.getAdminOperationPromotionCouponCodes as CouponCodesFetch,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  couponBid: string;
  couponName: string;
  fetchCodesApi?: CouponCodesFetch;
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
        const response = await fetchCodesApi({
          coupon_bid: couponBid,
          page_index: nextPage,
          page_size: PAGE_SIZE,
          keyword: nextKeyword,
        });
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
    [couponBid, fetchCodesApi, tPromotion],
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
          <DialogDescription className='sr-only'>
            {couponName || couponBid || tPromotion('coupon.codes')}
          </DialogDescription>
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
          <DialogDescription className='sr-only'>
            {campaignName || promoBid || tPromotion('campaign.redemptions')}
          </DialogDescription>
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
  fetchUsagesApi = api.getAdminOperationPromotionCouponUsages as CouponUsageFetch,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  couponBid: string;
  couponName: string;
  showCourseColumn: boolean;
  fetchUsagesApi?: CouponUsageFetch;
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
        const response = await fetchUsagesApi({
          coupon_bid: couponBid,
          page_index: nextPage,
          page_size: PAGE_SIZE,
        });
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
    [couponBid, fetchUsagesApi, tPromotion],
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
          <DialogDescription className='sr-only'>
            {couponName || couponBid || tPromotion('coupon.usages')}
          </DialogDescription>
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
