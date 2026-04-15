type LooseString = string & {};

export type AdminOperationCourseItem = {
  shifu_bid: string;
  course_name: string;
  course_status: string;
  price: string;
  creator_user_bid: string;
  creator_mobile: string;
  creator_email: string;
  creator_nickname: string;
  updater_user_bid: string;
  updater_mobile: string;
  updater_email: string;
  updater_nickname: string;
  created_at: string;
  updated_at: string;
};

export type AdminOperationCourseListResponse = {
  items: AdminOperationCourseItem[];
  page: number;
  page_count: number;
  page_size: number;
  total: number;
};

export type AdminOperationCourseDetailBasicInfo = {
  shifu_bid: string;
  course_name: string;
  course_status: string;
  creator_user_bid: string;
  creator_mobile: string;
  creator_email: string;
  creator_nickname: string;
  created_at: string;
  updated_at: string;
};

export type AdminOperationCourseDetailMetrics = {
  learner_count: number;
  order_count: number;
  order_amount: string;
  follow_up_count: number;
  rating_score: string;
};

export type AdminOperationCourseDetailChapter = {
  outline_item_bid: string;
  title: string;
  parent_bid: string;
  position: string;
  node_type: 'chapter' | 'lesson' | LooseString;
  learning_permission: 'guest' | 'free' | 'paid' | LooseString;
  is_visible: boolean;
  content_status: 'has' | 'empty' | LooseString;
  follow_up_count: number;
  rating_count: number;
  modifier_user_bid: string;
  modifier_mobile: string;
  modifier_email: string;
  modifier_nickname: string;
  updated_at: string;
  children: AdminOperationCourseDetailChapter[];
};

export type AdminOperationCourseChapterDetailResponse = {
  outline_item_bid: string;
  title: string;
  content: string;
  llm_system_prompt: string;
  llm_system_prompt_source: 'lesson' | 'chapter' | 'course' | '' | LooseString;
};

export type AdminOperationCourseDetailResponse = {
  basic_info: AdminOperationCourseDetailBasicInfo;
  metrics: AdminOperationCourseDetailMetrics;
  chapters: AdminOperationCourseDetailChapter[];
};

export type AdminOperationCourseUserRole =
  | 'operator'
  | 'creator'
  | 'student'
  | 'normal'
  | LooseString;

export type AdminOperationCourseUserLearningStatus =
  | 'not_started'
  | 'learning'
  | 'completed'
  | LooseString;

export type AdminOperationCourseUserItem = {
  user_bid: string;
  mobile: string;
  email: string;
  nickname: string;
  user_role: AdminOperationCourseUserRole;
  learned_lesson_count: number;
  total_lesson_count: number;
  learning_status: AdminOperationCourseUserLearningStatus;
  is_paid: boolean;
  total_paid_amount: string;
  last_learning_at: string;
  joined_at: string;
  last_login_at: string;
};

export type AdminOperationCourseUsersResponse = {
  items: AdminOperationCourseUserItem[];
  page: number;
  page_count: number;
  page_size: number;
  total: number;
};
