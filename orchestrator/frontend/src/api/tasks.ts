import { apiRequest, ApiError } from "./http";
import type { ReviewPayload, TaskCreatePayload, TaskData } from "../types/task";


export function createTask(payload: TaskCreatePayload): Promise<TaskData> {
  return apiRequest<TaskData>("/api/tasks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getTask(taskId: string): Promise<TaskData> {
  return apiRequest<TaskData>(`/api/tasks/${encodeURIComponent(taskId)}`);
}

export function resumeTask(taskId: string): Promise<TaskData> {
  return apiRequest<TaskData>(
    `/api/tasks/${encodeURIComponent(taskId)}/resume`,
    { method: "POST" },
  );
}

export async function getTaskReport(taskId: string): Promise<string> {
  const response = await fetch(
    `/api/tasks/${encodeURIComponent(taskId)}/report`,
  );
  if (!response.ok) {
    throw new ApiError(`报告读取失败（${response.status}）`, response.status);
  }
  return response.text();
}

export async function getTaskDiff(taskId: string): Promise<string> {
  const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/diff`);
  if (!response.ok) {
    throw new ApiError(`Diff 读取失败（${response.status}）`, response.status);
  }
  return response.text();
}

export function submitTaskReview(
  taskId: string,
  payload: ReviewPayload,
): Promise<TaskData> {
  return apiRequest<TaskData>(
    `/api/tasks/${encodeURIComponent(taskId)}/review`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}
