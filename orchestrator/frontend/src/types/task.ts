export type TaskStatus =
  | "accepted"
  | "running"
  | "pausing"
  | "paused"
  | "cancelling"
  | "cancelled"
  | "success"
  | "manual_review"
  | "infrastructure_error";

export type ReviewStatus =
  | "pending"
  | "approved"
  | "changes_requested"
  | "rejected"
  | "unavailable";

export type ReviewDecision = Exclude<ReviewStatus, "pending" | "unavailable">;
export type RunKind = "task" | "queue";

export interface TaskCreatePayload {
  requirement: string;
  acceptance_criteria: string[];
}

export interface ReviewPayload {
  decision: ReviewDecision;
  reviewer: string;
  comment: string;
  reviewed_diff_sha256: string;
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
  schema_version: number;
  legacy: boolean;
  history_warning: string | null;
  machine_status: TaskStatus | null;
  review_status: ReviewStatus;
  phase: string | null;
  thread_id: string | null;
  turn_count: number;
  failure_count: number;
  cycle_turn_count: number;
  cycle_failure_count: number;
  rounds: ValidationRound[];
  last_error_summary: string;
  infrastructure_error: string | null;
  started_at: string;
  updated_at: string;
  finished_at: string | null;
  report_url: string | null;
  diff_url: string | null;
  workspace: Record<string, unknown>;
  permissions: Record<string, unknown>;
  audit_summary: Record<string, unknown>;
  changed_files: Array<Record<string, unknown>>;
  codex_responses: Array<{ turn_number: number; response: string }>;
  final_diff_sha256: string;
  diff_redaction_count: number;
  review: Record<string, unknown> | null;
  review_history: Array<Record<string, unknown>>;
  queue_id: string | null;
  sequence: number | null;
  rerun_of: string | null;
}

export type QueueStatus =
  | "pending"
  | "running"
  | "pausing"
  | "paused"
  | "cancelling"
  | "cancelled"
  | "waiting_review"
  | "rejected"
  | "infrastructure_error"
  | "completed";

export type QueueSubtaskStatus =
  | "pending"
  | "running"
  | "pausing"
  | "paused"
  | "cancelling"
  | "cancelled"
  | "skipped"
  | "waiting_review"
  | "completed"
  | "rejected"
  | "infrastructure_error";

export interface QueueSubtaskCreatePayload extends TaskCreatePayload {}

export interface QueueCreatePayload {
  name: string;
  subtasks: QueueSubtaskCreatePayload[];
}

export interface QueueSubtaskData extends QueueSubtaskCreatePayload {
  task_id: string;
  sequence: number;
  status: QueueSubtaskStatus;
  machine_status: TaskStatus | null;
  review_status: ReviewStatus;
  thread_id: string | null;
  last_error_summary: string;
  updated_at: string;
}

export interface QueueData {
  queue_id: string;
  name: string;
  status: QueueStatus;
  base_ref: string;
  base_commit: string;
  current_task_id: string | null;
  cumulative_diff_sha256: string;
  last_error_summary: string;
  subtasks: QueueSubtaskData[];
  started_at: string;
  updated_at: string;
  finished_at: string | null;
  report_url: string | null;
  diff_url: string | null;
  rerun_of: string | null;
}

export interface ProjectData {
  project_id: string;
  name: string;
  repo_root: string;
  is_default: boolean;
  active_identifier: string | null;
}

export interface HistoryItemData {
  kind: RunKind;
  identifier: string;
  project_id: string;
  project_name: string;
  title: string;
  status: string;
  review_status: ReviewStatus | null;
  started_at: string;
  updated_at: string;
  finished_at: string | null;
  current_task_id: string | null;
}

export interface HistoryPageData {
  items: HistoryItemData[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface EventRecord {
  seq: number;
  type: string;
  event?: string;
  timestamp: string;
  task_id?: string;
  queue_id?: string;
  [key: string]: unknown;
}

export interface EventPageData {
  items: EventRecord[];
  next_cursor: number;
  terminal: boolean;
}

export interface LogData {
  log_id: string;
  name: string;
  size: number;
  sha256: string;
}

export interface NotificationData {
  notification_id: string;
  project_id: string;
  kind: RunKind;
  identifier: string;
  category: "waiting_review" | "completed" | "failure" | "cancelled";
  title: string;
  message: string;
  created_at: string;
  read_at: string | null;
  delivery: Record<string, string>;
}

export interface NotificationSettingsData {
  in_app: boolean;
  browser: boolean;
  email_configured: boolean;
  webhook_configured: boolean;
}

export interface HealthData {
  status: string;
  environment: string;
  version: string;
}

export interface ApiResponse<T> {
  success: boolean;
  data: T | null;
  message: string;
  request_id: string | null;
}
