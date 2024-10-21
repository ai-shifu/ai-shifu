import request from '../Service/Request';

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
  })
}

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
}

/**
 * @description 查询用户信息
 * @returns
 */
export const getUserInfo = () => {
  return request({
    url: '/api/user/info',
    method: 'get',
  })
}


/**
 *
 */
export const updateUserInfo = (name) => {
  return request({
    url: '/api/user/update_info',
    method: 'post',
    data: { name }
  })
}


export const updatePassword = (old_password, new_password) => {
  return request({
    url: '/api/user/update_password',
    method: 'post',
    data: { old_password, new_password }
  })
}

export const requireResetPasswordCode = (username) => {
  return request({
    url: '/api/user/require_reset_code',
    method: 'post',
    data: { username }
  })
}


export const resetPassword = (username, new_password, code) => {
  return request({
    url: '/api/user/reset_password',
    method: 'post',
    data: { username, new_password, code }
  })
}


export const requireTmp = (temp_id,source)=>{
  return request({
    url: '/api/user/require_tmp',
    method: 'post',
    data: { temp_id, source }
  });
}


/**
 *
 * @param {*} data
 * @returns
 *
 *  page_size = request.get_json().get('page_size',20)
        page_index = request.get_json().get('page_index',1)
        query = request.get_json().get('query',{})
 */

export const getUserList = (page_size,page_index,query) => {
  return request({
    url: '/api/user/user-list',
    method: 'post',
    data: {
      page_index,
      page_size,
      query

    }
  });
}
