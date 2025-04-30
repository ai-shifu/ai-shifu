// 模拟用户数据
interface User {
  id: string;
  email?: string;
  phone?: string;
  last_sign_in_at: string;
}

// 模拟存储的用户
const mockUsers = [
  {
    email: 'test@example.com',
    password: 'password123',
    id: 'user-1',
    last_sign_in_at: new Date().toISOString(),
  },
  {
    phone: '13800138000',
    id: 'user-2',
    last_sign_in_at: new Date().toISOString(),
  },
];

// 模拟认证服务
export const mockAuth = {
  // 当前用户
  currentUser: null as User | null,

  // 邮箱密码登录
  signInWithPassword: async ({
    email,
    password,
  }: {
    email: string;
    password: string;
  }) => {
    // 模拟网络延迟
    await new Promise((resolve) => setTimeout(resolve, 1000));

    const user = mockUsers.find(
      (u) => u.email === email && u.password === password,
    );

    if (!user) {
      return { error: { message: '邮箱或密码错误' } };
    }

    const userData = {
      id: user.id,
      email: user.email,
      last_sign_in_at: new Date().toISOString(),
    };

    mockAuth.currentUser = userData;
    localStorage.setItem('mockUser', JSON.stringify(userData));

    return { data: { user: userData }, error: null };
  },

  // 手机号登录/注册 - 发送OTP
  signInWithOtp: async ({}: { phone?: string; email?: string }) => {
    // 模拟网络延迟
    await new Promise((resolve) => setTimeout(resolve, 1000));

    // 模拟发送验证码成功
    return { error: null };
  },

  // 验证OTP (手机号)
  verifyOtp: async ({
    phone,
    token,
  }: {
    phone?: string;
    email?: string;
    token: string;
    type: string;
  }) => {
    // 模拟网络延迟
    await new Promise((resolve) => setTimeout(resolve, 1000));

    // 模拟验证码验证成功
    if (token === '123456' || token === '') {
      let userData;

      if (phone) {
        userData = {
          id: 'user-' + Math.floor(Math.random() * 1000),
          phone,
          last_sign_in_at: new Date().toISOString(),
        };
      } else {
        // 如果是邮箱验证，我们只返回成功，不创建用户
        return { data: { verified: true }, error: null };
      }

      mockAuth.currentUser = userData;
      localStorage.setItem('mockUser', JSON.stringify(userData));

      return { data: { user: userData }, error: null };
    }

    return { error: { message: '验证码错误' } };
  },

  // 注册
  signUp: async ({ email }: { email: string; password: string }) => {
    // 模拟网络延迟
    await new Promise((resolve) => setTimeout(resolve, 1000));

    // 模拟注册成功
    const userData = {
      id: 'user-' + Math.floor(Math.random() * 1000),
      email,
      last_sign_in_at: new Date().toISOString(),
    };

    mockAuth.currentUser = userData;
    localStorage.setItem('mockUser', JSON.stringify(userData));

    return { data: { user: userData }, error: null };
  },

  // 重置密码邮件 - 现在模拟发送验证码
  resetPasswordForEmail: async () => {
    // 模拟网络延迟
    await new Promise((resolve) => setTimeout(resolve, 1000));

    // 模拟发送验证码成功
    return { error: null };
  },

  // 更新用户
  updateUser: async ({}: { password: string }) => {
    // 模拟网络延迟
    await new Promise((resolve) => setTimeout(resolve, 1000));

    // 模拟更新密码成功
    return { error: null };
  },

  // 获取当前用户
  getUser: async () => {
    // 从本地存储获取用户
    const storedUser = localStorage.getItem('mockUser');
    const user = storedUser ? JSON.parse(storedUser) : null;
    mockAuth.currentUser = user;

    return { data: { user }, error: null };
  },

  // 退出登录
  signOut: async () => {
    // 清除本地存储的用户
    localStorage.removeItem('mockUser');
    mockAuth.currentUser = null;

    return { error: null };
  },
};
