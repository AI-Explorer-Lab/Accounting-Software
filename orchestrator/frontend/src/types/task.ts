export type TaskStatus =
  | "accepted"
  | "running"
  | "success"
  | "manual_review"
  | "infrastructure_error";

export interface TaskCreatePayload {
  requirement: string;
  acceptance_criteria: string[];
}

export interface CommandSummary {
  command: string[];
  stage: string;
  duration_seconds: number;
  exit_code: number | null;
  timed_out: boolean;
  infrastructure_error: string | null;
  log_path: string | null;
  passed: boolean;
}

export interface ValidationRound {
  round_number: number;
  passed: boolean;
  stage: string;
  started_at: string;
  finished_at: string | null;
  failure_summary: string;
  infrastructure_error: string | null;
  commands: CommandSummary[];
}

export interface TaskData {
  task_id: string;
  requirement: string;
  acceptance_criteria: string[];
  status: TaskStatus;
  phase: string | null;
  thread_id: string | null;
  turn_count: number;
  failure_count: number;
  rounds: ValidationRound[];
  last_error_summary: string;
  infrastructure_error: string | null;
  started_at: string;
  updated_at: string;
  finished_at: string | null;
  report_url: string | null;
}

export interface ApiResponse<T> {
  success: boolean;
  data: T | null;
  message: string;
  request_id: string | null;
}
