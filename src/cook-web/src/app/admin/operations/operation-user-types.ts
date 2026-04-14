type LooseString = string & {};

export type AdminOperationUserCourseItem = {
  shifu_bid: string;
  course_name: string;
  course_status: 'published' | 'unpublished' | LooseString;
  completed_lesson_count: number;
  total_lesson_count: number;
};

export type AdminOperationUserItem = {
  user_bid: string;
  mobile: string;
  email: string;
  nickname: string;
  user_status:
    | 'unregistered'
    | 'registered'
    | 'paid'
    | 'unknown'
    | LooseString;
  user_role:
    | 'regular'
    | 'creator'
    | 'operator'
    | 'learner'
    | 'unknown'
    | LooseString;
  user_roles: string[];
  login_methods: string[];
  registration_source:
    | 'phone'
    | 'email'
    | 'google'
    | 'wechat'
    | 'imported'
    | 'unknown'
    | LooseString;
  language: string;
  learning_courses: AdminOperationUserCourseItem[];
  created_courses: AdminOperationUserCourseItem[];
  total_paid_amount: string;
  last_login_at: string;
  last_learning_at: string;
  created_at: string;
  updated_at: string;
};

export type AdminOperationUserListResponse = {
  items: AdminOperationUserItem[];
  page: number;
  page_count: number;
  page_size: number;
  total: number;
};

export type AdminOperationUserDetailResponse = AdminOperationUserItem;
