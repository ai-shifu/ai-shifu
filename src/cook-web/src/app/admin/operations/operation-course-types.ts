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
