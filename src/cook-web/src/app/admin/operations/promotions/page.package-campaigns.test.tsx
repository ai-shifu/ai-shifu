import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import {
  resolvePackageCampaignProviderDiscountLabel,
  resolvePackageCampaignProductSummary,
  resolvePromotionStatusBadgeClassName,
} from './promotionPageShared';
import {
  mockCreatePackageCampaign,
  mockGetCoupons,
  mockGetPackageCampaignDetail,
  mockGetPackageCampaignProductOptions,
  mockGetPackageCampaigns,
  mockPublishPackageCampaignProviderDiscounts,
  mockToast,
  mockUpdatePackageCampaignStatus,
} from './promotionsTestUtils.test-support';
import AdminOperationPromotionsPage from './page';

describe('AdminOperationPromotionsPage package campaigns', () => {
  test('switches to package campaign tab and loads package campaigns', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.packageCampaigns',
      }),
    );

    await waitFor(() => {
      expect(mockGetPackageCampaigns).toHaveBeenCalledWith({
        page_index: 1,
        page_size: 20,
        keyword: '',
        product_type: '',
        benefit_type: '',
        status: '',
        start_time: '',
        end_time: '',
      });
    });
    expect(mockGetPackageCampaignProductOptions).toHaveBeenCalledWith({});
    expect(await screen.findByText('Spring Package Promo')).toBeInTheDocument();
    expect(
      screen.queryByText(
        'module.operationsPromotion.packageCampaign.campaignBid',
      ),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('module.operationsPromotion.table.createdAt'),
    ).not.toBeInTheDocument();
  });
  test('maps package campaign upcoming status and unknown product summary safely', () => {
    const tPromotion = (key: string) => `module.operationsPromotion.${key}`;

    expect(resolvePromotionStatusBadgeClassName('upcoming')).toBe(
      resolvePromotionStatusBadgeClassName('not_started'),
    );
    expect(
      resolvePackageCampaignProductSummary(tPromotion, {
        product_types: ['unknown'],
        product_count: 1,
      }),
    ).toBe('--');
    expect(
      resolvePackageCampaignProviderDiscountLabel(tPromotion, {
        benefit_type: 'discount',
        provider_discount_summary: { active: 1, total: 1 },
      }),
    ).toBe('module.operationsPromotion.packageCampaign.providerDiscountActive');
  });

  test('publishes package campaign provider discounts from row actions', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.packageCampaigns',
      }),
    );

    await waitFor(() => expect(mockGetPackageCampaigns).toHaveBeenCalled());
    const moreButtons = screen.getAllByRole('button', {
      name: 'common.core.more',
    });
    fireEvent.click(moreButtons[moreButtons.length - 1]);
    fireEvent.click(
      screen.getByText(
        'module.operationsPromotion.actions.publishProviderDiscounts',
      ),
    );

    await waitFor(() =>
      expect(mockPublishPackageCampaignProviderDiscounts).toHaveBeenCalledWith({
        campaign_bid: 'campaign-1',
      }),
    );
    expect(mockToast).toHaveBeenCalledWith({
      description:
        'module.operationsPromotion.messages.packageCampaignProviderPublished',
    });
  });
  test('opens package campaign product details from product column', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.packageCampaigns',
      }),
    );

    await screen.findByText('Spring Package Promo');

    const campaignRow = screen.getByText('Spring Package Promo').closest('tr');
    expect(campaignRow).not.toBeNull();

    fireEvent.click(
      within(campaignRow as HTMLElement).getByRole('button', {
        name: /module\.operationsPromotion\.packageCampaign\.productTypePlan/,
      }),
    );

    await waitFor(() => {
      expect(mockGetPackageCampaignDetail).toHaveBeenCalledWith({
        campaign_bid: 'campaign-1',
      });
    });

    expect(
      await screen.findByText(
        'module.operationsPromotion.packageCampaign.productDetails',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.catalog.plans.creatorMonthly.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'module.operationsPromotion.packageCampaign.productDetailsPercent',
      ),
    ).toBeInTheDocument();
  });
  test('creates a package campaign with the selected benefit and product payload', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.packageCampaigns',
      }),
    );

    await screen.findByText('Spring Package Promo');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.createPackageCampaign',
      }),
    );

    const dialogTitle = await screen.findByText(
      'module.operationsPromotion.packageCampaign.dialogTitle',
    );
    const dialog = dialogTitle.closest('div')?.parentElement?.parentElement;
    expect(dialog).not.toBeNull();
    const dialogScope = within(dialog as HTMLElement);

    fireEvent.change(
      dialogScope.getByPlaceholderText(
        'module.operationsPromotion.packageCampaign.namePlaceholder',
      ),
      {
        target: { value: 'May Bonus Campaign' },
      },
    );
    fireEvent.click(
      dialogScope.getByRole('button', {
        name: 'module.operationsPromotion.packageCampaign.productTypePlan',
      }),
    );
    fireEvent.click(
      dialogScope.getByRole('button', {
        name: 'module.operationsPromotion.packageCampaign.benefitTypeBonus',
      }),
    );
    fireEvent.click(dialogScope.getByRole('checkbox'));
    fireEvent.change(
      dialogScope.getByPlaceholderText(
        'module.operationsPromotion.packageCampaign.bonusCreditAmountPlaceholder',
      ),
      {
        target: { value: '88' },
      },
    );

    fireEvent.click(
      dialogScope.getByRole('button', {
        name: 'module.operationsPromotion.campaign.startAtPlaceholder',
      }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'select-date' }));
    fireEvent.click(
      screen.getByRole('button', {
        name: 'common.core.confirm',
      }),
    );

    fireEvent.click(
      dialogScope.getByRole('button', {
        name: 'module.operationsPromotion.campaign.endAtPlaceholder',
      }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'select-date' }));
    fireEvent.click(
      screen.getByRole('button', {
        name: 'common.core.confirm',
      }),
    );

    fireEvent.click(
      dialogScope.getByRole('button', {
        name: 'module.operationsPromotion.actions.confirmCreate',
      }),
    );

    await waitFor(() => {
      expect(mockCreatePackageCampaign).toHaveBeenCalledWith({
        name: 'May Bonus Campaign',
        note: '',
        benefit_type: 'bonus',
        products: [
          {
            product_bid: 'plan-1',
            discount_type: '',
            campaign_price_amount: 0,
            discount_percent: '',
            bonus_credit_amount: '88',
          },
        ],
        start_at: new Date('2026-04-24T00:00:00').toISOString(),
        end_at: new Date('2026-04-24T23:59:00').toISOString(),
      });
    });
  });
  test('shows a percent suffix for package campaign percentage rules', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.packageCampaigns',
      }),
    );

    await screen.findByText('Spring Package Promo');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.createPackageCampaign',
      }),
    );

    const dialogTitle = await screen.findByText(
      'module.operationsPromotion.packageCampaign.dialogTitle',
    );
    const dialog = dialogTitle.closest('div')?.parentElement?.parentElement;
    expect(dialog).not.toBeNull();
    const dialogScope = within(dialog as HTMLElement);

    fireEvent.click(
      dialogScope.getByRole('button', {
        name: 'module.operationsPromotion.packageCampaign.productTypePlan',
      }),
    );
    fireEvent.click(
      dialogScope.getByRole('button', {
        name: 'module.operationsPromotion.packageCampaign.benefitTypeDiscount',
      }),
    );
    fireEvent.click(
      dialogScope.getByRole('button', {
        name: 'module.operationsPromotion.discountType.percent',
      }),
    );
    fireEvent.click(dialogScope.getByRole('checkbox'));

    expect(
      dialogScope.queryByPlaceholderText(
        'module.operationsPromotion.packageCampaign.productDiscountPercentPlaceholder',
      ),
    ).not.toBeInTheDocument();
    expect(dialogScope.getByText('%')).toBeInTheDocument();
  });
  test('rejects zero package campaign fixed price before submit', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.packageCampaigns',
      }),
    );

    await screen.findByText('Spring Package Promo');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.createPackageCampaign',
      }),
    );

    const dialogTitle = await screen.findByText(
      'module.operationsPromotion.packageCampaign.dialogTitle',
    );
    const dialog = dialogTitle.closest('div')?.parentElement?.parentElement;
    expect(dialog).not.toBeNull();
    const dialogScope = within(dialog as HTMLElement);

    fireEvent.change(
      dialogScope.getByPlaceholderText(
        'module.operationsPromotion.packageCampaign.namePlaceholder',
      ),
      {
        target: { value: 'Zero Price Campaign' },
      },
    );
    fireEvent.click(
      dialogScope.getByRole('button', {
        name: 'module.operationsPromotion.packageCampaign.productTypePlan',
      }),
    );
    fireEvent.click(
      dialogScope.getByRole('button', {
        name: 'module.operationsPromotion.packageCampaign.benefitTypeDiscount',
      }),
    );
    fireEvent.click(dialogScope.getByRole('checkbox'));
    fireEvent.change(
      dialogScope.getByPlaceholderText(
        'module.operationsPromotion.packageCampaign.campaignPricePlaceholder',
      ),
      {
        target: { value: '0' },
      },
    );

    fireEvent.click(
      dialogScope.getByRole('button', {
        name: 'module.operationsPromotion.actions.confirmCreate',
      }),
    );

    expect(mockCreatePackageCampaign).not.toHaveBeenCalled();
    expect(mockToast).toHaveBeenCalledWith(
      expect.objectContaining({
        description:
          'module.operationsPromotion.validation.packageCampaignPriceInvalid',
      }),
    );
  });
  test('rejects invalid package campaign numeric inputs before submit', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.packageCampaigns',
      }),
    );

    await screen.findByText('Spring Package Promo');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.createPackageCampaign',
      }),
    );

    const dialogTitle = await screen.findByText(
      'module.operationsPromotion.packageCampaign.dialogTitle',
    );
    const dialog = dialogTitle.closest('div')?.parentElement?.parentElement;
    expect(dialog).not.toBeNull();
    const dialogScope = within(dialog as HTMLElement);

    fireEvent.change(
      dialogScope.getByPlaceholderText(
        'module.operationsPromotion.packageCampaign.namePlaceholder',
      ),
      {
        target: { value: 'Invalid Bonus Campaign' },
      },
    );
    fireEvent.click(
      dialogScope.getByRole('button', {
        name: 'module.operationsPromotion.packageCampaign.productTypePlan',
      }),
    );
    fireEvent.click(
      dialogScope.getByRole('button', {
        name: 'module.operationsPromotion.packageCampaign.benefitTypeBonus',
      }),
    );
    fireEvent.click(dialogScope.getByRole('checkbox'));
    fireEvent.change(
      dialogScope.getByPlaceholderText(
        'module.operationsPromotion.packageCampaign.bonusCreditAmountPlaceholder',
      ),
      {
        target: { value: 'abc' },
      },
    );

    fireEvent.click(
      dialogScope.getByRole('button', {
        name: 'module.operationsPromotion.actions.confirmCreate',
      }),
    );

    expect(mockCreatePackageCampaign).not.toHaveBeenCalled();
    expect(mockToast).toHaveBeenCalledWith(
      expect.objectContaining({
        description:
          'module.operationsPromotion.validation.packageCampaignBonusInvalid',
      }),
    );
  });
  test('hides the trial plan from package campaign product options', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.packageCampaigns',
      }),
    );

    await screen.findByText('Spring Package Promo');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.createPackageCampaign',
      }),
    );

    const dialogTitle = await screen.findByText(
      'module.operationsPromotion.packageCampaign.dialogTitle',
    );
    const dialog = dialogTitle.closest('div')?.parentElement?.parentElement;
    expect(dialog).not.toBeNull();
    const dialogScope = within(dialog as HTMLElement);

    fireEvent.click(
      dialogScope.getByRole('button', {
        name: 'module.operationsPromotion.packageCampaign.productTypePlan',
      }),
    );

    expect(
      dialogScope.queryByText('module.billing.catalog.plans.trial.title'),
    ).not.toBeInTheDocument();
    expect(
      dialogScope.getByText(
        'module.billing.catalog.plans.creatorMonthly.title',
      ),
    ).toBeInTheDocument();
  });
  test('updates package campaign status through the shared confirmation flow', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.packageCampaigns',
      }),
    );

    await screen.findByText('Spring Package Promo');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.disable',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.confirmDisable',
      }),
    );

    await waitFor(() => {
      expect(mockUpdatePackageCampaignStatus).toHaveBeenCalledWith({
        campaign_bid: 'campaign-1',
        enabled: false,
      });
    });
  });
});
