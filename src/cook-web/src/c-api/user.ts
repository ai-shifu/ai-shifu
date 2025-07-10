import request from '@/c-service/Request';
import { useSystemStore } from '@/c-store/useSystemStore';

/**
 * @description 用户注册接口
 * @param {*} username
 * @param {*} password
 * @param {*} name
 * @param {*} mobile
 * @param {*} email
 * @returns
 */
export const register = ({ username, password, mobile, email }) => {
  return request({
    url: '/api/user/register',
    method: 'post',
    data: { username, password, email, mobile }
  });
};

/**
 * 用户注册接口
 * @param {*} username
 * @param {*} password
 * @returns
 */
export const login = (username, password) => {
  return request({
    url: '/api/user/login',
    method: 'post',
    data: { username, password }
  });
};

/**
 * @description 查询用户信息
 * @returns
 */
export const getUserInfo = () => {
  return request({
    url: '/api/user/info',
    method: 'get',
  });
};


/**
 *
 */
export const updateUserInfo = (name) => {
  return request({
    url: '/api/user/update_info',
    method: 'post',
    data: { name }
  });
};


export const updatePassword = (old_password, new_password) => {
  return request({
    url: '/api/user/update_password',
    method: 'post',
    data: { old_password, new_password }
  });
};

export const requireResetPasswordCode = (username) => {
  return request({
    url: '/api/user/require_reset_code',
    method: 'post',
    data: { username }
  });
};


export const resetPassword = (username, new_password, code) => {
  return request({
    url: '/api/user/reset_password',
    method: 'post',
    data: { username, new_password, code }
  });
};

/**
 * 获取临时 token，在用户正常登录的时候，也需要有一个 token
 * @param tmp_id 客户端生成的 id，可以用来换 token
 * @returns
 *
 * https://agiclass.feishu.cn/docx/WyXhdgeVzoKVqDx1D4wc0eMknmg
 */
export const registerTmp = ({ temp_id }) => {
  const { channel: source, wechatCode: wxcode,language } = useSystemStore.getState();

  return request(
    {
      url: '/api/user/require_tmp',
      method: 'post',
      data: { temp_id, source, wxcode,language }
    }
  );
};

/**
 * 更新微信code
 * @returns
 */
export const updateWxcode = ({ wxcode }) => {
  // const { wechatCode: wxcode } = useSystemStore.getState();
  return request(
    {
      url: '/api/user/update_openid',
      method: 'post',
      data: { wxcode }
    }
  );
};

/**
 * 获取图形验证码
 */
export const genCheckCode = (mobile) => {
  return request({
    url: '/api/user/generate_chk_code',
    method: 'post',
    data: { mobile },
  });
};

/**
 * 发送手机验证码
 * @param {string} mobile 手机号
 * @param {string} check_code 图形验证码
 */
export const sendSmsCode = ({ mobile, check_code }) => {
  return request({
    url: '/api/user/send_sms_code',
    method: 'post',
    data: { mobile, check_code },
  });
};

// 获取用户详细信息
export const getUserProfile = (courseId) => {
  return request({
    url: '/api/user/get_profile',
    method: 'get',
    params: { course_id: courseId }
  });
};

// 上传头像
export const uploadAvatar = ({ avatar }) => {
  const formData = new FormData();
  formData.append('avatar', avatar);
  return request({
    headers: { 'Content-Type': 'multipart/form-data' },
    method: 'POST',
    url: '/api/user/upload_avatar',
    data: formData,
  });
};

// 更新用户详细信息
export const updateUserProfile = (data, courseId) => {
  return request({
    url: '/api/user/update_profile',
    method: 'POST',
    data: {
      "profiles": data,
      "course_id": courseId
    }
  });
};


// submit feedback
export const submitFeedback = (feedback) => {
  return request({
    url: '/api/user/submit-feedback',
    method: 'POST',
    data: {feedback}
  });
};
