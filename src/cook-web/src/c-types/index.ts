
import React from 'react';

export type ReactChangeEvent = React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>;
export type ReactMouseEvent = React.MouseEvent<HTMLElement, MouseEvent>;
export type ReactKeyboardEvent = React.KeyboardEvent<HTMLElement>;

export interface ApiResponse<T = any> {
  code: number;
  message: string;
  data?: T;
}

export interface UserInfo {
  token?: string;
  user_id?: string;
  username?: string;
  avatar?: string;
  phone?: string;
  language?: string;
  [key: string]: any;
}

export interface CourseInfo {
  course_id: string;
  course_name: string;
  course_desc: string;
  course_keywords: string;
  course_price: number;
  [key: string]: any;
}

export interface RouteParams {
  courseId?: string;
  lessonId?: string;
  [key: string]: string | undefined;
}
