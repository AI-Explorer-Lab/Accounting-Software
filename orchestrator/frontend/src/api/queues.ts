import { apiRequest, ApiError } from "./http";
import type { QueueCreatePayload, QueueData } from "../types/task";


export function createQueue(payload: QueueCreatePayload): Promise<QueueData> {
  return apiRequest<QueueData>("/api/queues", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getQueue(queueId: string): Promise<QueueData> {
  return apiRequest<QueueData>(`/api/queues/${encodeURIComponent(queueId)}`);
}

export function resumeQueue(queueId: string): Promise<QueueData> {
  return apiRequest<QueueData>(
    `/api/queues/${encodeURIComponent(queueId)}/resume`,
    { method: "POST" },
  );
}

export async function getQueueReport(queueId: string): Promise<string> {
  const response = await fetch(
    `/api/queues/${encodeURIComponent(queueId)}/report`,
  );
  if (!response.ok) {
    throw new ApiError(`长任务报告读取失败（${response.status}）`, response.status);
  }
  return response.text();
}

export async function getQueueDiff(queueId: string): Promise<string> {
  const response = await fetch(`/api/queues/${encodeURIComponent(queueId)}/diff`);
  if (!response.ok) {
    throw new ApiError(`累计 Diff 读取失败（${response.status}）`, response.status);
  }
  return response.text();
}
