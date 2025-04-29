// 验证中国大陆手机号（1开头的11位数字）
export function isValidPhoneNumber (phone: string): boolean {
  const phoneRegex = /^1[3-9]\d{9}$/
  return phoneRegex.test(phone)
}

// 验证邮箱格式
export function isValidEmail (email: string): boolean {
  const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/
  return emailRegex.test(email)
}

// 密码强度检查
export function checkPasswordStrength (password: string): {
  isValid: boolean
  score: number // 0-4, 0 = 非常弱, 4 = 非常强
  feedback: string[]
} {
  const feedback: string[] = []
  let score = 0

  // 检查长度
  if (password.length < 8) {
    feedback.push('密码长度至少为8个字符')
  } else {
    score += 1
  }

  // 检查是否包含数字
  if (!/\d/.test(password)) {
    feedback.push('密码应包含数字')
  } else {
    score += 1
  }

  // 检查是否包含小写字母
  if (!/[a-z]/.test(password)) {
    feedback.push('密码应包含小写字母')
  } else {
    score += 0.5
  }

  // 检查是否包含大写字母
  if (!/[A-Z]/.test(password)) {
    feedback.push('密码应包含大写字母')
  } else {
    score += 0.5
  }

  // 检查是否包含特殊字符
  if (!/[!@#$%^&*(),.?":{}|<>]/.test(password)) {
    feedback.push('密码应包含特殊字符')
  } else {
    score += 1
  }

  // 四舍五入得分
  score = Math.round(score)

  return {
    isValid: score >= 3 && password.length >= 8,
    score,
    feedback: feedback.slice(0, 1)
  }
}

// 获取密码强度描述
export function getPasswordStrengthText (score: number): string {
  switch (score) {
    case 0:
      return '非常弱'
    case 1:
      return '弱'
    case 2:
      return '中等'
    case 3:
      return '强'
    case 4:
      return '非常强'
    default:
      return '未知'
  }
}

// 获取密码强度颜色
export function getPasswordStrengthColor (score: number): string {
  switch (score) {
    case 0:
      return 'bg-red-500'
    case 1:
      return 'bg-orange-500'
    case 2:
      return 'bg-yellow-500'
    case 3:
      return 'bg-green-500'
    case 4:
      return 'bg-emerald-500'
    default:
      return 'bg-gray-300'
  }
}
