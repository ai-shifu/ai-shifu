export const LESSON_STATUS = {
  PREPARE_LEARNING: '可学习',
  NOT_START: '未开始',
  LOCKED: '未解锁',
  LEARNING: '正在学',
  COMPLETED: '已完成',
}

// 交互组件的展示类型
export const INTERACTION_DISPLAY_TYPE = {
  BUTTON: 'button', // 下一步
  TEXT: 'text', // 文本
  BUTTONS: 'buttons', // 按钮组
}

// 交互组件的功能类型
export const INTERACTION_TYPE = {
  CONTINUE: 'continue', // 下一步
  INPUT: 'input', // 文本
  BUTTONS: 'buttons', // 按钮组
  NEXT_CHAPTER: 'next_chapter', // 跳转下一章
  PHONE: 'phone', // 输入手机号
  CHECKCODE: 'checkcode', // 输入验证码
  ORDER: 'order', // 购买课程
  ASK: 'ask', // 追问
  REQUIRE_LOGIN: 'require_login', // 需要登录
}

// 交互组件的输出类型
export const INTERACTION_OUTPUT_TYPE = {
  START: 'start', // lesson 开始
  CONTINUE: 'continue', // 下一步
  TEXT: 'text', // 文本
  SELECT: 'select', // 多项选择
  NEXT_CHAPTER: 'next_chapter', // 跳转下一章
  PHONE: 'phone', // 输入手机号
  CHECKCODE: 'checkcode', // 输入短信验证码
  ORDER: 'order', // 购买课程
  ASK: 'ask', // 追问
  REQUIRE_LOGIN: 'require_login', // 需要登录
}

// sse 返回的事件类型
export const RESP_EVENT_TYPE = {
  TEXT: 'text',
  TEXT_END: 'text_end',
  BUTTONS: 'buttons',
  INPUT: 'input',
  LESSON_UPDATE: 'lesson_update',
  CHAPTER_UPDATE: 'chapter_update',
  PHONE: 'phone', // 输入手机号
  CHECKCODE: 'checkcode', // 输入短信验证码
  ORDER: 'order', // 购买课程
  ORDER_SUCCESS: 'order_success',
  USER_LOGIN: 'user_login', // 用户登录成功
  PROFILE_UPDATE: 'profile_update', // 用户信息更新
  ASK_MODE: 'ask_mode', // 追问模式
  TEACHER_AVATOR: 'teacher_avator', //
  REQUIRE_LOGIN: 'require_login', // need to login
}

// chat message 类型
export const CHAT_MESSAGE_TYPE ={
  TEXT: 'text',
  LESSON_SEPARATOR: 'lessonSeparator',
}
