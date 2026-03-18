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
  created_at: string;
  created_at_display?: string;
  chapter_count: number;
  learner_count: number;
};

export type DashboardCourseDetailMetrics = {
  order_count: number;
  order_amount: string;
  completed_learner_count: number;
  completion_rate: string;
  active_learner_count_last_7_days: number;
  total_follow_up_count: number;
  avg_follow_up_count_per_learner: string;
  avg_learning_duration_seconds: number;
};

export type DashboardCourseDetailQuestionsByChapterItem = {
  outline_item_bid: string;
  title: string;
  ask_count: number;
};

export type DashboardCourseDetailSeriesPoint = {
  label: string;
  value: number;
};

export type DashboardCourseDetailCharts = {
  questions_by_chapter: DashboardCourseDetailQuestionsByChapterItem[];
  questions_by_time: DashboardCourseDetailSeriesPoint[];
  learning_activity_trend: DashboardCourseDetailSeriesPoint[];
  chapter_progress_distribution: DashboardCourseDetailSeriesPoint[];
};

export type DashboardCourseDetailLearnerItem = {
  user_bid: string;
  nickname: string;
  progress_percent: string;
  follow_up_ask_count: number;
  last_active_at: string;
  last_active_at_display?: string;
};

export type DashboardCourseDetailLearners = {
  page: number;
  page_size: number;
  total: number;
  items: DashboardCourseDetailLearnerItem[];
};

export type DashboardCourseDetailAppliedRange = {
  start_date: string;
  end_date: string;
};

export type DashboardCourseDetailResponse = {
  basic_info: DashboardCourseDetailBasicInfo;
  metrics: DashboardCourseDetailMetrics;
  charts: DashboardCourseDetailCharts;
  learners: DashboardCourseDetailLearners;
  applied_range: DashboardCourseDetailAppliedRange;
};
