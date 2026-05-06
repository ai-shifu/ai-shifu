type LooseString = string & {};

export type AdminOperationCourseItem = {
  shifu_bid: string;
  course_name: string;
  course_status: string;
  price: string;
  course_model: string;
  has_course_prompt: boolean;
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

export type AdminOperationCourseOverview = {
  total_course_count: number;
  draft_course_count: number;
  published_course_count: number;
  created_last_7d_course_count: number;
  learning_active_30d_course_count: number;
  paid_order_30d_course_count: number;
};

export type AdminOperationCourseListResponse = {
  summary: AdminOperationCourseOverview;
  items: AdminOperationCourseItem[];
  page: number;
  page_count: number;
  page_size: number;
  total: number;
};

export type AdminOperationCoursePromptResponse = {
  course_prompt: string;
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
  visit_count_30d: number;
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
  rating_score: string;
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

export type AdminOperationCourseFollowUpSummary = {
  follow_up_count: number;
  user_count: number;
  lesson_count: number;
  latest_follow_up_at: string;
};

export type AdminOperationCourseFollowUpItem = {
  generated_block_bid: string;
  progress_record_bid: string;
  user_bid: string;
  mobile: string;
  email: string;
  nickname: string;
  chapter_outline_item_bid: string;
  chapter_title: string;
  lesson_outline_item_bid: string;
  lesson_title: string;
  follow_up_content: string;
  turn_index: number;
  created_at: string;
};

export type AdminOperationCourseFollowUpListResponse = {
  summary: AdminOperationCourseFollowUpSummary;
  items: AdminOperationCourseFollowUpItem[];
  page: number;
  page_size: number;
  total: number;
  page_count: number;
};

export type AdminOperationCourseRatingSummary = {
  average_score: string;
  rating_count: number;
  user_count: number;
  latest_rated_at: string;
};

export type AdminOperationCourseRatingItem = {
  lesson_feedback_bid: string;
  progress_record_bid: string;
  user_bid: string;
  mobile: string;
  email: string;
  nickname: string;
  chapter_outline_item_bid: string;
  chapter_title: string;
  lesson_outline_item_bid: string;
  lesson_title: string;
  score: number;
  comment: string;
  mode: 'read' | 'listen' | LooseString;
  rated_at: string;
};

export type AdminOperationCourseRatingListResponse = {
  summary: AdminOperationCourseRatingSummary;
  items: AdminOperationCourseRatingItem[];
  page: number;
  page_size: number;
  total: number;
  page_count: number;
};

export type AdminOperationCourseFollowUpDetailBasicInfo = {
  generated_block_bid: string;
  progress_record_bid: string;
  user_bid: string;
  mobile: string;
  email: string;
  nickname: string;
  course_name: string;
  shifu_bid: string;
  chapter_title: string;
  lesson_title: string;
  created_at: string;
  turn_index: number;
};

export type AdminOperationCourseFollowUpCurrentRecord = {
  follow_up_content: string;
  answer_content: string;
  source_output_content: string;
  source_output_type: string;
  source_position: number;
  source_element_bid: string;
  source_element_type: string;
};

export type AdminOperationCourseFollowUpTimelineRole =
  | 'student'
  | 'teacher'
  | LooseString;

export type AdminOperationCourseFollowUpTimelineItem = {
  role: AdminOperationCourseFollowUpTimelineRole;
  content: string;
  created_at: string;
  is_current: boolean;
};

export type AdminOperationCourseFollowUpDetailResponse = {
  basic_info: AdminOperationCourseFollowUpDetailBasicInfo;
  current_record: AdminOperationCourseFollowUpCurrentRecord;
  timeline: AdminOperationCourseFollowUpTimelineItem[];
};
