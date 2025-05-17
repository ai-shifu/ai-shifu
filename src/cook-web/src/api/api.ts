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
  // auth
  login: 'POST /user/login',
  sendSmsCode: 'POST /user/send_sms_code',
  sendMailCode: 'POST /user/send_mail_code',
  requireTmp: 'POST /user/require_tmp',
  verifyMailCode: 'POST /user/verify_mail_code',
  verifySmsCode: 'POST /user/verify_sms_code',
  setPassword: 'POST /user/set_user_password',
  submitFeedback: 'POST /user/submit-feedback',

  getShifuList: 'GET /shifu/shifu-list',
  createShifu: 'POST /shifu/create-shifu',
  getShifuChapters: 'GET /shifu/chapters',
  createChapter: 'POST /shifu/create-chapter',
  createUnit: 'POST /shifu/create-unit',
  deleteChapter: 'POST /shifu/delete-chapter',
  deleteUnit: 'POST /shifu/delete-unit',
  markFavoriteShifu: 'POST /shifu/mark-favorite-shifu',
  modifyChapter: 'POST /shifu/modify-chapter',
  getShifuOutlineTree: 'GET /shifu/outline-tree',
  getBlocks: 'GET /shifu/blocks',
  saveBlocks: 'POST /shifu/save-blocks',
  getProfile: 'GET /user/get_profile',
  getProfileItemDefinitions: 'GET /profiles/get-profile-item-definitions',
  getProfileItemOptionList:
    'GET /profiles/get-profile-item-definition-option-list',
  addProfileItem: 'POST /profiles/add-profile-item-quick',
  getUserInfo: 'GET /user/info',
  updateUserInfo: 'POST /user/update_info',
  updateChapterOrder: 'POST /shifu/update-chapter-order',
  addBlock: 'POST /shifu/add-block',
  publishShifu: 'POST /shifu/publish-shifu',
  previewShifu: 'POST /shifu/preview-shifu',
  modifyUnit: 'POST /shifu/modify-unit',
  getUnitInfo: 'GET /shifu/unit-info',
  getShifuInfo: 'GET /shifu/shifu-info',
  getShifuDetail: 'GET /shifu/shifu-detail',
  saveShifuDetail: 'POST /shifu/save-shifu-detail',
  getModelList: 'GET /llm/model-list',
  getSystemPrompt: 'GET /llm/get-system-prompt',
  debugPrompt: 'GET /llm/debug-prompt',

  // profile

  saveProfile: 'POST /profiles/save-profile-item',
  deleteProfile: 'POST /profiles/delete-profile-item',
  getProfileList: 'GET /profiles/get-profile-item-definitions'
}

export default api
