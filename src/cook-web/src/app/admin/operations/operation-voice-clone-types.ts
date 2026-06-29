export type AdminOperationVoiceCloneItem = {
  voice_bid: string;
  display_name: string;
  voice_id: string;
  owner_user_bid: string;
  owner_mobile: string;
  owner_email: string;
  owner_nickname: string;
  shifu_bid: string;
  course_name: string;
  course_status: string;
  status: string;
  status_msg: string;
  failure_reason: string;
  retry_count: number;
  source_capture_method: string;
  source_audio_duration_ms: number;
  normalized_audio_duration_ms: number;
  prompt_audio_duration_ms: number;
  minimax_source_file_id: string;
  minimax_prompt_file_id: string;
  minimax_trace_id: string;
  minimax_status_code: number;
  minimax_status_msg: string;
  billing_status: string;
  estimated_credits: string;
  charged_credits: string;
  billing_reservation_bid: string;
  billing_ledger_bid: string;
  clone_usage_bid: string;
  created_at: string;
  updated_at: string;
  ready_at: string;
};

export type AdminOperationVoiceCloneListResponse = {
  items: AdminOperationVoiceCloneItem[];
  page: number;
  page_size: number;
  total: number;
  page_count: number;
};

export type AdminOperationVoiceCloneFilters = {
  status: string;
  failure_reason: string;
  billing_status: string;
  start_time: string;
  end_time: string;
  user_keyword: string;
  course_keyword: string;
  voice_keyword: string;
  minimax_status_code: string;
};
