/**
 * Interface URL
 * login ---- The specific request method name used in business
 * GET ---- The method passed to axios
 * /auth/login  ----- The interface URL
 * There must be a mandatory space between method and URL in http, which will be uniformly parsed
 *
 * Support defining dynamic parameters in the URL and then passing parameters to the request method according to the actual scenario in the business, assigning them to dynamic parameters
 * eg  /auth/:userId/login
 *     userId is a dynamic parameter
 *     Parameter assignment: login({userId: 1})
 */

const api = {
  // config
  getRuntimeConfig: 'GET /config',

  // auth
  getCaptcha: 'GET /user/captcha',
  verifyCaptcha: 'POST /user/captcha/verify',
  sendSmsCode: 'POST /user/send_sms_code',
  sendEmailCode: 'POST /user/send_email_code',
  requireTmp: 'POST /user/require_tmp',
  smsLogin: 'POST /user/login_sms',
  submitFeedback: 'POST /user/submit-feedback',
  googleOauthStart: 'GET /user/oauth/google',
  googleOauthCallback: 'GET /user/oauth/google/callback',
  ensureAdminCreator: 'POST /user/ensure_admin_creator',
  getCreatorOnboardingStatus: 'GET /user/onboarding/status',
  completeCreatorOnboarding: 'POST /user/onboarding/complete',
  loginPassword: 'POST /user/login_password',
  setPassword: 'POST /user/set_password',
  changePassword: 'POST /user/change_password',
  resetPassword: 'POST /user/reset_password',
  getProfileOnboarding: 'GET /user/profile-onboarding',
  completeProfileOnboarding: 'POST /user/profile-onboarding/complete',

  // referral api
  getReferralInviteProfile: 'GET /referral/invite-profile',
  getReferralInvitePreview: 'GET /referral/invite-preview',
  recordReferralInviteEvent: 'POST /referral/invite-event',

  // shifu api start
  getShifuList: 'GET /shifu/shifus',
  createShifu: 'PUT /shifu/shifus',
  getShifuDetail: 'GET /shifu/shifus/{shifu_bid}/detail',
  getShifuDraftMeta: 'GET /shifu/shifus/{shifu_bid}/draft-meta',
  saveShifuDetail: 'POST /shifu/shifus/{shifu_bid}/detail',
  publishShifu: 'POST /shifu/shifus/{shifu_bid}/publish',
  previewShifu: 'POST /shifu/shifus/{shifu_bid}/preview',
  archiveShifu: 'POST /shifu/shifus/{shifu_bid}/archive',
  unarchiveShifu: 'POST /shifu/shifus/{shifu_bid}/unarchive',
  listShifuPermissions: 'GET /shifu/shifus/{shifu_bid}/permissions',
  grantShifuPermissions: 'POST /shifu/shifus/{shifu_bid}/permissions/grant',
  removeShifuPermission: 'POST /shifu/shifus/{shifu_bid}/permissions/remove',
  previewOutlineBlock: 'POST /learn/shifu/{shifu_bid}/preview/{outline_bid}',
  // shifu api end

  // outline api start
  getShifuOutlineTree: 'GET /shifu/shifus/{shifu_bid}/outlines',
  createOutline: 'PUT /shifu/shifus/{shifu_bid}/outlines',
  deleteOutline: 'DELETE /shifu/shifus/{shifu_bid}/outlines/{outline_bid}',
  modifyOutline: 'POST /shifu/shifus/{shifu_bid}/outlines/{outline_bid}',
  getOutlineInfo: 'GET /shifu/shifus/{shifu_bid}/outlines/{outline_bid}',
  reorderOutlineTree: 'PATCH /shifu/shifus/{shifu_bid}/outlines/reorder',

  getMdflow: 'GET /shifu/shifus/{shifu_bid}/outlines/{outline_bid}/mdflow',
  saveMdflow: 'POST /shifu/shifus/{shifu_bid}/outlines/{outline_bid}/mdflow',
  parseMdflow:
    'POST /shifu/shifus/{shifu_bid}/outlines/{outline_bid}/mdflow/parse',
  getMdflowHistory:
    'GET /shifu/shifus/{shifu_bid}/outlines/{outline_bid}/mdflow/history',
  getMdflowHistoryVersionDetail:
    'GET /shifu/shifus/{shifu_bid}/outlines/{outline_bid}/mdflow/history/{version_id}',
  restoreMdflowHistory:
    'POST /shifu/shifus/{shifu_bid}/outlines/{outline_bid}/mdflow/history/restore',
  runMdflow: 'POST /shifu/shifus/{shifu_bid}/outlines/{outline_bid}/mdflow/run',
  // outline api end

  // blocks api
  getBlocks: 'GET /shifu/shifus/{shifu_bid}/outlines/{outline_bid}/blocks',
  saveBlocks: 'POST /shifu/shifus/{shifu_bid}/outlines/{outline_bid}/blocks',
  addBlock: 'PUT /shifu/shifus/{shifu_bid}/outlines/{outline_bid}/blocks',
  // block api end

  getProfile: 'GET /user/get_profile',
  getProfileItemDefinitions: 'GET /profiles/get-profile-item-definitions',
  addProfileItem: 'POST /profiles/add-profile-item-quick',
  getUserInfo: 'GET /user/info',
  updateUserInfo: 'POST /user/update_info',
  updateChapterOrder: 'POST /shifu/update-chapter-order',

  getModelList: 'GET /llm/model-list',
  getSystemPrompt: 'GET /llm/get-system-prompt',
  debugPrompt: 'GET /llm/debug-prompt',

  // resource api start
  getVideoInfo: 'POST /shifu/get-video-info',
  upfileByUrl: 'POST /shifu/url-upfile',
  // resource api end

  // TTS api
  askConfig: 'GET /shifu/ask/config',
  askPreview: 'POST /shifu/ask/preview',
  ttsPreview: 'POST /shifu/tts/preview',
  ttsConfig: 'GET /shifu/tts/config',
  listMinimaxTtsVoices: 'GET /shifu/tts/minimax/voices',
  getMinimaxTtsVoice: 'GET /shifu/tts/minimax/voices/{voice_bid}',
  retryMinimaxTtsVoice: 'POST /shifu/tts/minimax/voices/{voice_bid}/retry',
  deleteMinimaxTtsVoice: 'DELETE /shifu/tts/minimax/voices/{voice_bid}',
  getMinimaxTtsCloneCost: 'GET /shifu/tts/minimax/voices/clone-cost',
  validateMinimaxTtsVoiceId: 'POST /shifu/tts/minimax/voices/validate-id',
  // admin order api
  getAdminOrders: 'GET /order/admin/orders',
  getAdminOrderDetail: 'GET /order/admin/orders/{order_bid}',
  getAdminOrderShifus: 'GET /order/admin/orders/shifus',
  importActivationOrder: 'POST /order/admin/orders/import-activation',
  getCreatorCourseRedemptionCodes: 'GET /order/admin/orders/redemption-codes',
  createCreatorCourseRedemptionCode:
    'POST /order/admin/orders/redemption-codes',
  getCreatorCourseRedemptionCodeDetail:
    'GET /order/admin/orders/redemption-codes/{coupon_bid}',
  updateCreatorCourseRedemptionCode:
    'POST /order/admin/orders/redemption-codes/{coupon_bid}',
  updateCreatorCourseRedemptionCodeStatus:
    'POST /order/admin/orders/redemption-codes/{coupon_bid}/status',
  getCreatorCourseRedemptionCodeUsages:
    'GET /order/admin/orders/redemption-codes/{coupon_bid}/usages',
  getCreatorCourseRedemptionCodeCodes:
    'GET /order/admin/orders/redemption-codes/{coupon_bid}/codes',
  getAdminOperationUsersOverview: 'GET /shifu/admin/operations/users/overview',
  getAdminOperationUsers: 'GET /shifu/admin/operations/users',
  getAdminOperationOrdersOverview:
    'GET /shifu/admin/operations/orders/overview',
  getAdminOperationOrders: 'GET /shifu/admin/operations/orders',
  getAdminOperationOrderDetail:
    'GET /shifu/admin/operations/orders/{order_bid}/detail',
  getAdminOperationCreditOrdersOverview:
    'GET /shifu/admin/operations/orders/credits/overview',
  getAdminOperationCreditOrders: 'GET /shifu/admin/operations/orders/credits',
  getAdminOperationCreditOrderDetail:
    'GET /shifu/admin/operations/orders/credits/{bill_order_bid}/detail',
  getAdminOperationPromotionCoupons:
    'GET /shifu/admin/operations/promotions/coupons',
  createAdminOperationPromotionCoupon:
    'POST /shifu/admin/operations/promotions/coupons',
  updateAdminOperationPromotionCoupon:
    'POST /shifu/admin/operations/promotions/coupons/{coupon_bid}',
  getAdminOperationPromotionCouponDetail:
    'GET /shifu/admin/operations/promotions/coupons/{coupon_bid}',
  updateAdminOperationPromotionCouponStatus:
    'POST /shifu/admin/operations/promotions/coupons/{coupon_bid}/status',
  getAdminOperationPromotionCouponUsages:
    'GET /shifu/admin/operations/promotions/coupons/{coupon_bid}/usages',
  getAdminOperationPromotionCouponCodes:
    'GET /shifu/admin/operations/promotions/coupons/{coupon_bid}/codes',
  getAdminOperationPromotionCampaigns:
    'GET /shifu/admin/operations/promotions/campaigns',
  createAdminOperationPromotionCampaign:
    'POST /shifu/admin/operations/promotions/campaigns',
  getAdminOperationPromotionCampaignDetail:
    'GET /shifu/admin/operations/promotions/campaigns/{promo_bid}',
  updateAdminOperationPromotionCampaign:
    'POST /shifu/admin/operations/promotions/campaigns/{promo_bid}',
  updateAdminOperationPromotionCampaignStatus:
    'POST /shifu/admin/operations/promotions/campaigns/{promo_bid}/status',
  getAdminOperationPromotionCampaignRedemptions:
    'GET /shifu/admin/operations/promotions/campaigns/{promo_bid}/redemptions',
  getAdminOperationPromotionReferralCampaigns:
    'GET /shifu/admin/operations/promotions/referral-campaigns',
  createAdminOperationPromotionReferralCampaign:
    'POST /shifu/admin/operations/promotions/referral-campaigns',
  getAdminOperationPromotionReferralCampaignDetail:
    'GET /shifu/admin/operations/promotions/referral-campaigns/{campaign_bid}',
  updateAdminOperationPromotionReferralCampaign:
    'POST /shifu/admin/operations/promotions/referral-campaigns/{campaign_bid}',
  updateAdminOperationPromotionReferralCampaignStatus:
    'POST /shifu/admin/operations/promotions/referral-campaigns/{campaign_bid}/status',
  getAdminOperationPromotionReferralCampaignRelations:
    'GET /shifu/admin/operations/promotions/referral-campaigns/{campaign_bid}/relations',
  getAdminOperationPromotionReferralCampaignInvitations:
    'GET /shifu/admin/operations/promotions/referral-campaigns/{campaign_bid}/invitations',
  getAdminOperationUserDetail:
    'GET /shifu/admin/operations/users/{user_bid}/detail',
  getAdminOperationUserCredits:
    'GET /shifu/admin/operations/users/{user_bid}/credits',
  getAdminOperationUserCreditUsageDetail:
    'GET /shifu/admin/operations/users/{user_bid}/credits/usages/{usage_bid}/detail',
  getAdminOperationUserGrantBootstrap:
    'GET /shifu/admin/operations/users/{user_bid}/credit-grant/bootstrap',
  grantAdminOperationUserCredits:
    'POST /shifu/admin/operations/users/{user_bid}/credits/grant',
  grantAdminOperationUserPackage:
    'POST /shifu/admin/operations/users/{user_bid}/packages/grant',
  getAdminOperationCreditNotifications:
    'GET /shifu/admin/operations/credit-notifications',
  getAdminOperationVoiceClones: 'GET /shifu/admin/operations/voice-clones',
  registerAdminOperationVoiceClone: 'POST /shifu/admin/operations/voice-clones',
  getAdminOperationCreditNotificationsOverview:
    'GET /shifu/admin/operations/credit-notifications/overview',
  getAdminOperationCreditNotificationDetail:
    'GET /shifu/admin/operations/credit-notifications/{notification_bid}',
  getAdminOperationCreditNotificationConfig:
    'GET /shifu/admin/operations/credit-notifications/config',
  updateAdminOperationCreditNotificationConfig:
    'POST /shifu/admin/operations/credit-notifications/config',
  syncAdminOperationCreditNotificationTemplate:
    'POST /shifu/admin/operations/credit-notifications/templates/sync',
  getAdminOperationCreditNotificationTemplates:
    'GET /shifu/admin/operations/credit-notifications/templates',
  dryRunAdminOperationCreditNotifications:
    'POST /shifu/admin/operations/credit-notifications/dry-run',
  requeueAdminOperationCreditNotification:
    'POST /shifu/admin/operations/credit-notifications/{notification_bid}/requeue',
  getAdminOperationProfileOnboardingConfig:
    'GET /shifu/admin/operations/profile-onboarding',
  updateAdminOperationProfileOnboardingConfig:
    'POST /shifu/admin/operations/profile-onboarding',
  getAdminOperationConfigRates: 'GET /shifu/admin/operations/config/rates',
  updateAdminOperationConfigRate: 'POST /shifu/admin/operations/config/rates',
  getAdminOperationReferrals: 'GET /shifu/admin/operations/referrals',
  getAdminOperationReferralsOverview:
    'GET /shifu/admin/operations/referrals/overview',
  getAdminOperationReferralDetail:
    'GET /shifu/admin/operations/referrals/{relation_bid}',
  updateAdminOperationReferralStatus:
    'POST /shifu/admin/operations/referrals/{relation_bid}/status',
  adjustAdminOperationReferral:
    'POST /shifu/admin/operations/referrals/{relation_bid}/adjustment',
  getAdminOperationCoursesOverview:
    'GET /shifu/admin/operations/courses/overview',
  getAdminOperationCourses: 'GET /shifu/admin/operations/courses',
  getAdminOperationCoursePrompt:
    'GET /shifu/admin/operations/courses/{shifu_bid}/prompt',
  getAdminOperationCourseDetail:
    'GET /shifu/admin/operations/courses/{shifu_bid}/detail',
  getAdminOperationCourseUsers:
    'GET /shifu/admin/operations/courses/{shifu_bid}/users',
  getAdminOperationCourseCreditUsages:
    'GET /shifu/admin/operations/courses/{shifu_bid}/credit-usages',
  getAdminOperationCourseCreditUsageDetails:
    'GET /shifu/admin/operations/courses/{shifu_bid}/credit-usages/details',
  getAdminOperationCourseRatings:
    'GET /shifu/admin/operations/courses/{shifu_bid}/ratings',
  getAdminOperationCourseFollowUps:
    'GET /shifu/admin/operations/courses/{shifu_bid}/follow-ups',
  getAdminOperationCourseFollowUpDetail:
    'GET /shifu/admin/operations/courses/{shifu_bid}/follow-ups/{generated_block_bid}/detail',
  getAdminOperationCourseChapterDetail:
    'GET /shifu/admin/operations/courses/{shifu_bid}/chapters/{outline_item_bid}/detail',
  copyAdminOperationCourse:
    'POST /shifu/admin/operations/courses/{shifu_bid}/copy',
  transferAdminOperationCourseCreator:
    'POST /shifu/admin/operations/courses/{shifu_bid}/transfer-creator',

  // profile

  saveProfile: 'POST /profiles/save-profile-item',
  deleteProfile: 'POST /profiles/delete-profile-item',
  getProfileList: 'GET /profiles/get-profile-item-definitions',
  hideUnusedProfileItems: 'POST /profiles/hide-unused-profile-items',
  getProfileVariableUsage: 'GET /profiles/profile-variable-usage',
  updateProfileHiddenState: 'POST /profiles/update-profile-hidden-state',

  // MDF Conversion
  genMdfConvert: 'POST /gen_mdf/convert',
  genMdfConfigStatus: 'GET /gen_mdf/config-status',

  // dashboard (teacher analytics)
  getDashboardEntry: 'GET /dashboard/entry',
  getDashboardCourseDetail: 'GET /dashboard/shifus/{shifu_bid}/detail',
  getDashboardCourseLearners: 'GET /dashboard/shifus/{shifu_bid}/learners',
  getDashboardCourseRatings: 'GET /dashboard/shifus/{shifu_bid}/ratings',
  getDashboardCourseFollowUps: 'GET /dashboard/shifus/{shifu_bid}/follow-ups',
  getDashboardCourseFollowUpDetail:
    'GET /dashboard/shifus/{shifu_bid}/follow-ups/{generated_block_bid}/detail',

  // billing creator api
  getBillingBootstrap: 'GET /billing',
  getBillingCatalog: 'GET /billing/catalog',
  getBillingOverview: 'GET /billing/overview',
  acknowledgeBillingTrialWelcome: 'POST /billing/trial-offer/welcome/ack',
  getBillingWalletBuckets: 'GET /billing/wallet-buckets',
  getBillingLedger: 'GET /billing/ledger',
  checkoutBillingOrder: 'POST /billing/orders/{bill_order_bid}/checkout',
  syncBillingOrder: 'POST /billing/orders/{bill_order_bid}/sync',
  checkoutBillingSubscription: 'POST /billing/subscriptions/checkout',
  cancelBillingSubscription: 'POST /billing/subscriptions/cancel',
  resumeBillingSubscription: 'POST /billing/subscriptions/resume',
  checkoutBillingTopup: 'POST /billing/topups/checkout',
  getBillingCustomization: 'GET /billing/customization',
  updateBillingBranding: 'PUT /billing/customization/branding',
  createBillingDomain: 'POST /billing/customization/domains',
  verifyBillingDomain:
    'POST /billing/customization/domains/{domain_binding_bid}/verify',
  disableBillingDomain:
    'DELETE /billing/customization/domains/{domain_binding_bid}',
  saveBillingIntegration: 'PUT /billing/customization/integrations/{provider}',
  verifyBillingIntegration:
    'POST /billing/customization/integrations/{provider}/verify',
  disableBillingIntegration:
    'DELETE /billing/customization/integrations/{provider}',

  // billing admin api
  getAdminBillingSubscriptions: 'GET /admin/billing/subscriptions',
  getAdminBillingCampaignProductOptions: 'GET /admin/billing/products/options',
  getAdminBillingCampaigns: 'GET /admin/billing/campaigns',
  createAdminBillingCampaign: 'POST /admin/billing/campaigns',
  getAdminBillingCampaignDetail: 'GET /admin/billing/campaigns/{campaign_bid}',
  updateAdminBillingCampaign: 'POST /admin/billing/campaigns/{campaign_bid}',
  updateAdminBillingCampaignStatus:
    'POST /admin/billing/campaigns/{campaign_bid}/status',
  getAdminBillingEntitlements: 'GET /admin/billing/entitlements',
  grantAdminBillingEntitlement: 'POST /admin/billing/entitlements/grants',
  getAdminBillingOpsState: 'GET /admin/billing/ops-state',
  updateAdminBillingConfigStatus: 'POST /admin/billing/ops-state/config-status',
  getAdminBillingCustomization:
    'GET /admin/billing/customization/{creator_bid}',
  getAdminBillingCustomizationDraft: 'GET /admin/billing/customization-draft',
  saveAdminBillingCustomizationDraft: 'PUT /admin/billing/customization-draft',
  deleteAdminBillingCustomizationDraft:
    'DELETE /admin/billing/customization-draft',
  updateAdminBillingCustomizationBranding:
    'PUT /admin/billing/customization/{creator_bid}/branding',
  uploadAdminBillingCustomizationDraftLogo:
    'POST /admin/billing/customization-draft/branding/logo',
  createAdminBillingCustomizationDomain:
    'POST /admin/billing/customization/{creator_bid}/domains',
  verifyAdminBillingCustomizationDomain:
    'POST /admin/billing/customization/{creator_bid}/domains/{domain_binding_bid}/verify',
  disableAdminBillingCustomizationDomain:
    'DELETE /admin/billing/customization/{creator_bid}/domains/{domain_binding_bid}',
  saveAdminBillingCustomizationIntegration:
    'PUT /admin/billing/customization/{creator_bid}/integrations/{provider}',
  verifyAdminBillingCustomizationIntegration:
    'POST /admin/billing/customization/{creator_bid}/integrations/{provider}/verify',
  disableAdminBillingCustomizationIntegration:
    'DELETE /admin/billing/customization/{creator_bid}/integrations/{provider}',
  getAdminBillingFocusTeachers: 'GET /admin/billing/reports/focus-teachers',
  getAdminBillingDailyUsageMetrics: 'GET /admin/billing/reports/usage-daily',
  getAdminBillingDailyLedgerSummary: 'GET /admin/billing/reports/ledger-daily',
};

export default api;
