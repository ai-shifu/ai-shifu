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

export type DashboardCourseDetailSectionChart = {
  chapter_outline_item_bid: string;
  chapter_title: string;
  section_outline_item_bid: string;
  section_title: string;
  position: string;
  learning_user_count: number;
  learning_record_count: number;
  follow_up_user_count: number;
  follow_up_question_count: number;
};

export type DashboardCourseDetailCharts = {
  sections: DashboardCourseDetailSectionChart[];
};

export type DashboardCourseDetailResponse = {
  basic_info: DashboardCourseDetailBasicInfo;
  metrics: DashboardCourseDetailMetrics;
  charts: DashboardCourseDetailCharts;
};
