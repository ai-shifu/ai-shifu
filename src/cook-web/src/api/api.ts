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
  sendSmsCode: 'POST /user/send_sms_code',
  sendEmailCode: 'POST /user/send_email_code',
  requireTmp: 'POST /user/require_tmp',
  verifySmsCode: 'POST /user/verify_sms_code',
  submitFeedback: 'POST /user/submit-feedback',
  googleOauthStart: 'GET /user/oauth/google',
  googleOauthCallback: 'GET /user/oauth/google/callback',
  ensureAdminCreator: 'POST /user/ensure_admin_creator',
  loginPassword: 'POST /user/login_password',
  setPassword: 'POST /user/set_password',
  changePassword: 'POST /user/change_password',
  resetPassword: 'POST /user/reset_password',

  // shifu api start
  getShifuList: 'GET /shifu/shifus',
  createShifu: 'PUT /shifu/shifus',
  getShifuDetail: 'GET /shifu/shifus/{shifu_bid}/detail',
  saveShifuDetail: 'POST /shifu/shifus/{shifu_bid}/detail',
  publishShifu: 'POST /shifu/shifus/{shifu_bid}/publish',
  previewShifu: 'POST /shifu/shifus/{shifu_bid}/preview',
  archiveShifu: 'POST /shifu/shifus/{shifu_bid}/archive',
  unarchiveShifu: 'POST /shifu/shifus/{shifu_bid}/unarchive',
  previewOutlineBlock: 'POST /learn/shifu/{shifu_bid}/preview/{outline_bid}',
  // shifu api end

  markFavoriteShifu: 'POST /shifu/mark-favorite-shifu',

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
  runMdflow: 'POST /shifu/shifus/{shifu_bid}/outlines/{outline_bid}/mdflow/run',
  // outline api end

  // blocks api
  getBlocks: 'GET /shifu/shifus/{shifu_bid}/outlines/{outline_bid}/blocks',
  saveBlocks: 'POST /shifu/shifus/{shifu_bid}/outlines/{outline_bid}/blocks',
  addBlock: 'PUT /shifu/shifus/{shifu_bid}/outlines/{outline_bid}/blocks',
  // block api end

  getProfile: 'GET /user/get_profile',
  getProfileItemDefinitions: 'GET /profiles/get-profile-item-definitions',
  getProfileItemOptionList:
    'GET /profiles/get-profile-item-definition-option-list',
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
  ttsPreview: 'POST /shifu/tts/preview',
  ttsConfig: 'GET /shifu/tts/config',
  // admin order api
  getAdminOrders: 'GET /order/admin/orders',
  getAdminOrderDetail: 'GET /order/admin/orders/{order_bid}',
  getAdminOrderShifus: 'GET /order/admin/orders/shifus',
  importActivationOrder: 'POST /order/admin/orders/import-activation',

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
};

export default api;
