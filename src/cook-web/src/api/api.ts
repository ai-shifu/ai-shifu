
/**
 * 接口url
 * login ---- 业务调用的具体的请求方法名
 * GET ---- 传递给axios的method
 * /auth/login  ----- 接口url
 * method和url中间强制空格一个，在http中会统一解析
 *
 * 支持在url中定义动态参数，然后在业务中根据实际场景给请求方法传递参数，赋值给动态参数
 * eg  /auth/:userId/login
 *     userId为动态参数
 *     参数赋值： login({userId: 1})
 */
const api = {
    login: 'POST /user/login', //token
    register: 'POST /user/register',
    getScenarioList: 'GET /scenario/scenarios',
    createScenario: "POST /scenario/create-scenario",
    getScenarioChapters: "GET /scenario/chapters",
    createChapter: "POST /scenario/create-chapter",
    deleteChapter: "POST /scenario/delete-chapter",
    markFavoriteScenario: "POST /scenario/mark-favorite-scenario",
    modifyChapter: "POST /scenario/modify-chapter",
    getScenarioOutlineTree: "GET /scenario/outline-tree"
};

export default api;
