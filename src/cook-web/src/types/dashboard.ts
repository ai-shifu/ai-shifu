export type DashboardEntrySummary = {
  course_count: number;
  learner_count: number;
  order_count: number;
  order_amount: string;
};

export type DashboardEntryCourseItem = {
  shifu_bid: string;
  shifu_name: string;
  learner_count: number;
  order_count: number;
  order_amount: string;
  last_active_at: string;
  last_active_at_display?: string;
};

export type DashboardEntryResponse = {
  summary: DashboardEntrySummary;
  page: number;
  page_count: number;
  page_size: number;
  total: number;
  items: DashboardEntryCourseItem[];
};

export type DashboardCourseDetailBasicInfo = {
  shifu_bid: string;
  course_name: string;
  course_status: 'published' | 'unpublished' | string;
  created_at: string;
  created_at_display?: string;
  chapter_count: number;
  learner_count: number;
};

export type DashboardCourseDetailMetrics = {
  order_count: number;
  order_amount: string;
  new_learner_count_last_7_days: number;
  learning_learner_count: number;
  completed_learner_count: number;
  completion_rate: string;
  active_learner_count_last_7_days: number;
  total_follow_up_count: number;
  rating_score: string;
};

export type DashboardCourseDetailLearnerItem = {
  user_bid: string;
  mobile: string;
  email: string;
  nickname: string;
  learned_lesson_count: number;
  total_lesson_count: number;
  learning_status: 'not_started' | 'learning' | 'completed' | string;
  follow_up_count: number;
  last_learning_at: string;
  last_learning_at_display?: string;
  joined_at: string;
  joined_at_display?: string;
};

export type DashboardCourseDetailLearners = {
  page: number;
  page_count: number;
  page_size: number;
  total: number;
  items: DashboardCourseDetailLearnerItem[];
};

export type DashboardCourseDetailResponse = {
  basic_info: DashboardCourseDetailBasicInfo;
  metrics: DashboardCourseDetailMetrics;
};

export type DashboardCourseLearnersResponse = DashboardCourseDetailLearners;

export type DashboardCourseFollowUpSummary = {
  follow_up_count: number;
  user_count: number;
  lesson_count: number;
  latest_follow_up_at: string;
};

export type DashboardCourseFollowUpItem = {
  generated_block_bid: string;
  progress_record_bid: string;
  user_bid: string;
  mobile: string;
  email: string;
  nickname: string;
  chapter_title: string;
  lesson_title: string;
  follow_up_content: string;
  turn_index: number;
  created_at: string;
};

export type DashboardCourseFollowUpListResponse = {
  summary: DashboardCourseFollowUpSummary;
  page: number;
  page_count: number;
  page_size: number;
  total: number;
  items: DashboardCourseFollowUpItem[];
};

export type DashboardCourseFollowUpDetailBasicInfo = {
  generated_block_bid: string;
  progress_record_bid: string;
  user_bid: string;
  mobile: string;
  email: string;
  nickname: string;
  chapter_title: string;
  lesson_title: string;
  created_at: string;
  turn_index: number;
};

export type DashboardCourseFollowUpCurrentRecord = {
  follow_up_content: string;
  answer_content: string;
};

export type DashboardCourseFollowUpTimelineItem = {
  role: 'student' | 'teacher' | string;
  content: string;
  created_at: string;
  is_current: boolean;
};

export type DashboardCourseFollowUpDetailResponse = {
  basic_info: DashboardCourseFollowUpDetailBasicInfo;
  current_record: DashboardCourseFollowUpCurrentRecord;
  timeline: DashboardCourseFollowUpTimelineItem[];
};

export type DashboardCourseRatingSummary = {
  average_score: string;
  rating_count: number;
  user_count: number;
  latest_rated_at: string;
};

export type DashboardCourseRatingItem = {
  lesson_feedback_bid: string;
  progress_record_bid: string;
  user_bid: string;
  mobile: string;
  email: string;
  nickname: string;
  chapter_title: string;
  lesson_title: string;
  score: number;
  comment: string;
  rated_at: string;
};

export type DashboardCourseRatingListResponse = {
  summary: DashboardCourseRatingSummary;
  page: number;
  page_count: number;
  page_size: number;
  total: number;
  items: DashboardCourseRatingItem[];
};
