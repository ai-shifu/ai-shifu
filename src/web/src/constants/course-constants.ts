export const LESSON_STATUS_VALUE = {
  PREPARE_LEARNING: 'not_started',
  LEARNING: 'in_progress',
  COMPLETED: 'completed',
  LOCKED: 'locked',

  // no use in project
  // REFUND: 604,
  // UNAVAILABLE: 606,
  // BRANCH: 607,
  // RESET: 608,
};
// Display types for interaction components
export const INTERACTION_DISPLAY_TYPE = {
  BUTTON: 'button', // Next-step button
  TEXT: 'text', // Text block
  BUTTONS: 'buttons', // Button group
};

// Functional types for interaction components
export const INTERACTION_TYPE = {
  CONTINUE: 'continue', // Next step
  INPUT: 'input', // Text input
  BUTTONS: 'buttons', // Button group
  NEXT_CHAPTER: 'next_chapter', // Jump to the next chapter
  PHONE: 'phone', // Enter phone number
  CHECKCODE: 'checkcode', // Enter verification code
  ORDER: 'order', // Purchase course
  ASK: 'ask', // Follow-up question
  REQUIRE_LOGIN: 'require_login', // Requires login
  NONBLOCK_ORDER: 'nonblock_order', // Purchase dialog that keeps the conversation going
};

// Output types for interaction components
export const INTERACTION_OUTPUT_TYPE = {
  START: 'start', // Lesson start
  CONTINUE: 'continue', // Next step
  TEXT: 'text', // Text block
  SELECT: 'select', // Multiple choice
  NEXT_CHAPTER: 'next_chapter', // Jump to the next chapter
  PHONE: 'phone', // Enter phone number
  CHECKCODE: 'checkcode', // Enter SMS verification code
  ORDER: 'order', // Purchase course
  NONBLOCK_ORDER: 'nonblock_order', // Purchase dialog that keeps the conversation going
  ASK: 'ask', // Follow-up question
  REQUIRE_LOGIN: 'require_login', // Requires login
  LOGIN: 'login', // Log in
};

// SSE event types returned by the backend
export const RESP_EVENT_TYPE = {
  TEXT: 'text',
  TEXT_END: 'text_end',
  BUTTONS: 'buttons',
  INPUT: 'input',
  LESSON_UPDATE: 'lesson_update',
  CHAPTER_UPDATE: 'chapter_update',
  PHONE: 'phone', // Enter phone number
  CHECKCODE: 'checkcode', // Enter SMS verification code
  ORDER: 'order', // Purchase course
  NONBLOCK_ORDER: 'nonblock_order', // Purchase dialog that keeps the conversation going
  ORDER_SUCCESS: 'order_success',
  USER_LOGIN: 'user_login', // User login succeeded
  PROFILE_UPDATE: 'profile_update', // User profile updated
  ASK_MODE: 'ask_mode', // Follow-up question mode
  TEACHER_AVATOR: 'teacher_avator', // Teacher avatar
  REQUIRE_LOGIN: 'require_login', // need to login
  ACTIVE: 'active', // ask activity
};

// Chat message types
export const CHAT_MESSAGE_TYPE = {
  ACTIVE: 'active', // ask activity
  TEXT: 'text',
  LESSON_SEPARATOR: 'lessonSeparator',
};
