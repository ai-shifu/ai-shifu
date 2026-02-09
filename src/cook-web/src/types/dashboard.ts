export type DashboardPage<T> = {
  items: T[];
  page: number;
  page_count: number;
  page_size: number;
  total: number;
};

export type DashboardOutline = {
  outline_item_bid: string;
  title: string;
  type: number;
  hidden: boolean;
  parent_bid: string;
  position: string;
};

export type DashboardSeriesPoint = {
  label: string;
  value: number;
};

export type DashboardTopOutline = {
  outline_item_bid: string;
  title: string;
  ask_count: number;
};

export type DashboardTopLearner = {
  user_bid: string;
  nickname: string;
  mobile: string;
  ask_count: number;
};

export type DashboardOverviewKpis = {
  learner_count: number;
  completion_count: number;
  completion_rate: number;
  required_outline_total: number;
  follow_up_ask_total: number;
};

export type DashboardOverview = {
  kpis: DashboardOverviewKpis;
  progress_distribution: DashboardSeriesPoint[];
  follow_up_trend: DashboardSeriesPoint[];
  top_outlines_by_follow_ups: DashboardTopOutline[];
  top_learners_by_follow_ups: DashboardTopLearner[];
  start_date: string;
  end_date: string;
};

export type DashboardLearnerSummary = {
  user_bid: string;
  nickname: string;
  mobile: string;
  required_outline_total: number;
  completed_outline_count: number;
  progress_percent: number;
  last_active_at: string;
  follow_up_ask_count: number;
};

export type DashboardLearnerVariable = {
  key: string;
  value: string;
};

export type DashboardLearnerOutlineProgress = {
  outline_item_bid: string;
  title: string;
  type: number;
  hidden: boolean;
  status: number;
  block_position: number;
  updated_at: string;
};

export type DashboardLearnerFollowUpSummary = {
  total_ask_count: number;
  by_outline: DashboardTopOutline[];
};

export type DashboardLearnerDetail = {
  user_bid: string;
  nickname: string;
  mobile: string;
  outlines: DashboardLearnerOutlineProgress[];
  variables: DashboardLearnerVariable[];
  followups: DashboardLearnerFollowUpSummary;
};

export type DashboardFollowUpItem = {
  outline_item_bid: string;
  outline_title: string;
  position: number;
  asked_at: string;
  question: string;
  answered_at: string;
  answer: string;
};
