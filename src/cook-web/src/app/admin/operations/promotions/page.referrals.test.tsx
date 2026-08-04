import './promotionsTestUtils.test-support';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import AdminOperationPromotionsPage from './page';
import {
  MOCK_DIALOG_CLOSE_LABEL,
  mockCreateReferralCampaign,
  mockGetCoupons,
  mockGetPackageCampaignProductOptions,
  mockGetReferralCampaignDetail,
  mockGetReferralCampaignInvitations,
  mockGetReferralCampaignRelations,
  mockGetReferralCampaigns,
  mockUpdateReferralCampaignStatus,
} from './promotionsTestUtils.test-support';

describe('AdminOperationPromotionsPage referral campaigns', () => {
  test('switches to referral campaign tab and loads referral campaigns', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.referralCampaigns',
      }),
    );

    await waitFor(() => {
      expect(mockGetReferralCampaigns).toHaveBeenCalledWith({
        page_index: 1,
        page_size: 20,
        keyword: '',
        status: '',
        start_time: '',
        end_time: '',
      });
    });
    expect(mockGetPackageCampaignProductOptions).toHaveBeenCalledWith({});
    expect(
      await screen.findByText('Domestic Creator Invite'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.catalog.plans.creatorMonthly.title'),
    ).toBeInTheDocument();
    expect(screen.getByText('1,000')).toBeInTheDocument();
    expect(screen.getByText('14')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('8')).toBeInTheDocument();
    expect(screen.getByText('21')).toBeInTheDocument();
  });
  test('opens referral campaign records dialog from referral campaign row', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.referralCampaigns',
      }),
    );

    await screen.findByText('Domestic Creator Invite');

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'module.operationsPromotion.actions.viewData: module.operationsPromotion.referralCampaign.inviteCodeCount',
      }),
    );

    expect(
      await screen.findByText(
        'module.operationsPromotion.referralCampaign.records.title',
      ),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(mockGetReferralCampaignInvitations).toHaveBeenCalledWith(
        expect.objectContaining({
          campaign_bid: 'ref-campaign-1',
          page_index: 1,
          page_size: 20,
        }),
      );
    });
    expect(await screen.findByText('ABC12345')).toBeInTheDocument();
    expect(screen.getByText('13800000000')).toBeInTheDocument();

    const closeButtons = screen.getAllByRole('button', {
      name: MOCK_DIALOG_CLOSE_LABEL,
    });
    fireEvent.click(closeButtons[closeButtons.length - 1]);

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'module.operationsPromotion.actions.viewData: module.operationsPromotion.referralCampaign.relationCount',
      }),
    );

    await waitFor(() => {
      expect(mockGetReferralCampaignRelations).toHaveBeenCalledWith(
        expect.objectContaining({
          campaign_bid: 'ref-campaign-1',
          page_index: 1,
          page_size: 20,
        }),
      );
    });
  });
  test('normalizes referral reward credits when opening the edit dialog', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.referralCampaigns',
      }),
    );

    await screen.findByText('Domestic Creator Invite');

    const moreButtons = screen.getAllByRole('button', {
      name: 'common.core.more',
    });
    fireEvent.click(moreButtons[moreButtons.length - 1]);
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'module.operationsPromotion.actions.edit',
      }),
    );

    await waitFor(() => {
      expect(mockGetReferralCampaignDetail).toHaveBeenCalledWith({
        campaign_bid: 'ref-campaign-1',
      });
    });

    const rewardCreditsInput = await screen.findByDisplayValue('1000');
    expect(rewardCreditsInput).toBeInTheDocument();
  });
  test('creates a referral campaign with full configuration payload', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.referralCampaigns',
      }),
    );

    await screen.findByText('Domestic Creator Invite');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.createReferralCampaign',
      }),
    );

    const dialogTitle = await screen.findByText(
      'module.operationsPromotion.referralCampaign.dialogTitle',
    );
    const dialog = dialogTitle.closest('div')?.parentElement?.parentElement;
    expect(dialog).not.toBeNull();
    const dialogScope = within(dialog as HTMLElement);

    fireEvent.change(
      dialogScope.getByPlaceholderText(
        'module.operationsPromotion.referralCampaign.namePlaceholder',
      ),
      {
        target: { value: 'July Referral Campaign' },
      },
    );
    fireEvent.change(
      dialogScope.getByPlaceholderText(
        'module.operationsPromotion.referralCampaign.codePlaceholder',
      ),
      {
        target: { value: 'july_referral' },
      },
    );
    fireEvent.click(
      dialogScope.getByRole('button', {
        name: 'module.billing.catalog.plans.creatorMonthly.title',
      }),
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
      expect(mockCreateReferralCampaign).toHaveBeenCalledWith({
        campaign_code: 'july_referral',
        campaign_name: 'July Referral Campaign',
        enabled: true,
        starts_at: new Date('2026-04-24T00:00:00').toISOString(),
        ends_at: new Date('2026-04-24T23:59:00').toISOString(),
        reward_product_code: 'creator-plan-monthly',
        reward_cycle_count: 1,
        reward_credit_amount: '1000',
        reward_credit_validity_days: 30,
        reward_cap_scope: 'per_inviter',
        reward_cap_count: 12,
        feature_flag_key: '',
        invite_route_template: '/invite/{invite_code}',
        inviter_eligibility: {},
        invitee_eligibility: {},
        invitee_benefit_policy: 'existing_trial_only',
        rules_copy_i18n_key: '',
        rule_code: '',
        priority: 0,
      });
    });
  });
  test('updates referral campaign status through the shared confirmation flow', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.referralCampaigns',
      }),
    );

    await screen.findByText('Domestic Creator Invite');

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
      expect(mockUpdateReferralCampaignStatus).toHaveBeenCalledWith({
        campaign_bid: 'ref-campaign-1',
        enabled: false,
      });
    });
  });
});
