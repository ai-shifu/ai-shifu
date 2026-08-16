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
