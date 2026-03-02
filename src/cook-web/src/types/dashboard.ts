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
};

export type DashboardEntryResponse = {
  summary: DashboardEntrySummary;
  page: number;
  page_count: number;
  page_size: number;
  total: number;
  items: DashboardEntryCourseItem[];
};
