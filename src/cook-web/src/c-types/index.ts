import React from 'react';
export type ReactMouseEvent = React.MouseEvent<HTMLElement, MouseEvent>;

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
  is_creator?: boolean;
  is_operator?: boolean;
  [key: string]: any;
}
