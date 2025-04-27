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
  register: 'POST /user/register',
  sendSmsCode: 'POST /user/send_sms_code',
  sendMailCode: 'POST /user/send_mail_code',
  requireTmp: 'POST /user/require_tmp',
  verifyMailCode: 'POST /user/verify_mail_code',
  verifySmsCode: 'POST /user/verify_sms_code',
  setPassword: 'POST /user/set_user_password',
  submitFeedback: 'POST /user/submit-feedback',

  getScenarioList: 'GET /scenario/scenarios',
  createScenario: 'POST /scenario/create-scenario',
  getScenarioChapters: 'GET /scenario/chapters',
  createChapter: 'POST /scenario/create-chapter',
  createUnit: 'POST /scenario/create-unit',
  deleteChapter: 'POST /scenario/delete-chapter',
  deleteUnit: 'POST /scenario/delete-unit',
  markFavoriteScenario: 'POST /scenario/mark-favorite-scenario',
  modifyChapter: 'POST /scenario/modify-chapter',
  getScenarioOutlineTree: 'GET /scenario/outline-tree',
  getBlocks: 'GET /scenario/blocks',
  saveBlocks: 'POST /scenario/save-blocks',
  getProfile: 'GET /user/get_profile',
  getProfileItemDefinitions: 'GET /profiles/get-profile-item-definitions',
  getProfileItemOptionList:
    'GET /profiles/get-profile-item-definition-option-list',
  addProfileItem: 'POST /profiles/add-profile-item-quick',
  getUserInfo: 'GET /user/info',
  updateChapterOrder: 'POST /scenario/update-chapter-order',
  addBlock: 'POST /scenario/add-block',
  publishScenario: 'POST /scenario/publish-scenario',
  previewScenario: 'POST /scenario/preview-scenario',
  modifyUnit: 'POST /scenario/modify-unit',
  getUnitInfo: 'GET /scenario/unit-info',
  getScenarioInfo: 'GET /scenario/scenario-info',
  getScenarioDetail: 'GET /scenario/scenario-detail',
  saveScenarioDetail: 'POST /scenario/save-scenario-detail',
  getModelList: 'GET /llm/model-list',
  getSystemPrompt: 'GET /llm/get-system-prompt',
  debugPrompt: 'GET /llm/debug-prompt',

  // profile

  saveProfile: 'POST /profiles/save-profile-item',
  deleteProfile: 'POST /profiles/delete-profile-item',
  getProfileList: 'GET /profiles/get-profile-item-definitions'
}

export default api
