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

export type DashboardCourseDetailResponse = {
  basic_info: DashboardCourseDetailBasicInfo;
  metrics: DashboardCourseDetailMetrics;
};
