<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";

import {
  createQueue,
  getQueue,
  getQueueDiff,
  getQueueReport,
} from "./api/queues";
import {
  createTask,
  getTask,
  getTaskDiff,
  getTaskReport,
  submitTaskReview,
} from "./api/tasks";
import QueueForm from "./components/QueueForm.vue";
import QueueProgress from "./components/QueueProgress.vue";
import ReportPanel from "./components/ReportPanel.vue";
import TaskForm from "./components/TaskForm.vue";
import TaskStatus from "./components/TaskStatus.vue";
import ValidationRounds from "./components/ValidationRounds.vue";
import type {
  QueueCreatePayload,
  QueueData,
  ReviewDecision,
  TaskCreatePayload,
  TaskData,
} from "./types/task";


const TASK_STORAGE_KEY = "codex-orchestrator:last-task-id";
const QUEUE_STORAGE_KEY = "codex-orchestrator:last-queue-id";
const LAST_KIND_STORAGE_KEY = "codex-orchestrator:last-kind";
const POLL_INTERVAL_MS = 2_000;
const FINAL_TASK_STATUSES = new Set<TaskData["status"]>([
  "success",
  "manual_review",
  "infrastructure_error",
]);
const ACTIVE_QUEUE_STATUSES = new Set<QueueData["status"]>([
  "pending",
  "running",
  "waiting_review",
  "infrastructure_error",
]);

const mode = ref<"single" | "queue">("single");
const task = ref<TaskData | null>(null);
const queue = ref<QueueData | null>(null);
const report = ref("");
const diff = ref("");
const queueReport = ref("");
const queueDiff = ref("");
const submitting = ref(false);
const reviewing = ref(false);
const pageError = ref("");
let pollTimer: ReturnType<typeof setTimeout> | null = null;

const taskIsActive = computed(
  () =>
    submitting.value ||
    task.value?.status === "accepted" ||
    task.value?.status === "running" ||
    (queue.value !== null && ACTIVE_QUEUE_STATUSES.has(queue.value.status)),
);

function clearPollTimer(): void {
  if (pollTimer !== null) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function scheduleTaskPoll(taskId: string): void {
  clearPollTimer();
  pollTimer = setTimeout(() => void refreshTask(taskId), POLL_INTERVAL_MS);
}

function scheduleQueuePoll(queueId: string): void {
  clearPollTimer();
  pollTimer = setTimeout(() => void refreshQueue(queueId), POLL_INTERVAL_MS);
}

async function loadTaskArtifacts(taskId: string): Promise<void> {
  try {
    const requests: Promise<void>[] = [];
    if (task.value?.report_url) {
      requests.push(getTaskReport(taskId).then((value) => { report.value = value; }));
    }
    if (task.value?.diff_url) {
      requests.push(getTaskDiff(taskId).then((value) => { diff.value = value; }));
    } else {
      diff.value = "";
    }
    await Promise.all(requests);
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : "任务记录读取失败。";
  }
}

async function loadQueueArtifacts(queueId: string): Promise<void> {
  try {
    const requests: Promise<void>[] = [];
    if (queue.value?.report_url) {
      requests.push(getQueueReport(queueId).then((value) => { queueReport.value = value; }));
    }
    if (queue.value?.diff_url) {
      requests.push(getQueueDiff(queueId).then((value) => { queueDiff.value = value; }));
    }
    await Promise.all(requests);
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : "长任务记录读取失败。";
  }
}

async function refreshTask(taskId: string): Promise<void> {
  try {
    const latest = await getTask(taskId);
    task.value = latest;
    pageError.value = "";
    if (FINAL_TASK_STATUSES.has(latest.status)) {
      clearPollTimer();
      await loadTaskArtifacts(taskId);
      return;
    }
    scheduleTaskPoll(taskId);
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : "任务状态读取失败。";
    scheduleTaskPoll(taskId);
  }
}

async function loadQueueTask(taskId: string): Promise<void> {
  try {
    const latest = await getTask(taskId);
    task.value = latest;
    if (FINAL_TASK_STATUSES.has(latest.status)) {
      await loadTaskArtifacts(taskId);
    }
  } catch {
    // The queue can be persisted just before its child run directory appears.
  }
}

async function refreshQueue(queueId: string): Promise<void> {
  try {
    const latest = await getQueue(queueId);
    queue.value = latest;
    pageError.value = "";
    if (latest.current_task_id) {
      await loadQueueTask(latest.current_task_id);
    }
    await loadQueueArtifacts(queueId);
    if (latest.status === "pending" || latest.status === "running") {
      scheduleQueuePoll(queueId);
      return;
    }
    clearPollTimer();
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : "长任务状态读取失败。";
    scheduleQueuePoll(queueId);
  }
}

async function submitTask(payload: TaskCreatePayload): Promise<void> {
  submitting.value = true;
  resetDisplayedRun();
  try {
    const accepted = await createTask(payload);
    task.value = accepted;
    localStorage.setItem(TASK_STORAGE_KEY, accepted.task_id);
    localStorage.setItem(LAST_KIND_STORAGE_KEY, "single");
    scheduleTaskPoll(accepted.task_id);
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : "任务提交失败。";
  } finally {
    submitting.value = false;
  }
}

async function submitQueue(payload: QueueCreatePayload): Promise<void> {
  submitting.value = true;
  resetDisplayedRun();
  try {
    const accepted = await createQueue(payload);
    queue.value = accepted;
    localStorage.setItem(QUEUE_STORAGE_KEY, accepted.queue_id);
    localStorage.setItem(LAST_KIND_STORAGE_KEY, "queue");
    scheduleQueuePoll(accepted.queue_id);
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : "长任务提交失败。";
  } finally {
    submitting.value = false;
  }
}

function resetDisplayedRun(): void {
  pageError.value = "";
  report.value = "";
  diff.value = "";
  queueReport.value = "";
  queueDiff.value = "";
  task.value = null;
  queue.value = null;
  clearPollTimer();
}

async function submitReview(payload: {
  decision: ReviewDecision;
  reviewer: string;
  comment: string;
}): Promise<void> {
  if (!task.value) return;
  reviewing.value = true;
  pageError.value = "";
  try {
    task.value = await submitTaskReview(task.value.task_id, {
      ...payload,
      reviewed_diff_sha256: task.value.final_diff_sha256,
    });
    if (queue.value) {
      await refreshQueue(queue.value.queue_id);
    } else {
      await loadTaskArtifacts(task.value.task_id);
    }
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : "审查提交失败。";
  } finally {
    reviewing.value = false;
  }
}

onMounted(() => {
  const lastKind = localStorage.getItem(LAST_KIND_STORAGE_KEY);
  const previousQueueId = localStorage.getItem(QUEUE_STORAGE_KEY);
  const previousTaskId = localStorage.getItem(TASK_STORAGE_KEY);
  if (lastKind === "queue" && previousQueueId) {
    mode.value = "queue";
    void refreshQueue(previousQueueId);
  } else if (previousTaskId) {
    void refreshTask(previousTaskId);
  }
});

onUnmounted(clearPollTimer);
</script>

<template>
  <div class="app-shell">
    <header class="hero">
      <div class="hero-copy">
        <p class="eyebrow">LOCAL DEVELOPMENT WORKFLOW</p>
        <h1>把需求交给 Codex，<br />把过程留在眼前。</h1>
        <p class="hero-description">
          单个功能可以直接执行；长任务由你拆成有顺序的子任务，逐个通过机器验证和人工审查后继续。
        </p>
      </div>
      <div class="hero-mark" aria-hidden="true">
        <span>01</span><div /><span>CODEX</span>
      </div>
    </header>

    <main>
      <section class="panel form-panel">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">新任务</p>
            <h2>描述你希望完成的功能</h2>
          </div>
          <span class="local-pill">仅在本机运行</span>
        </div>
        <div class="mode-switch" role="tablist" aria-label="任务类型">
          <button
            type="button"
            :class="{ active: mode === 'single' }"
            :disabled="taskIsActive"
            data-test="single-mode"
            @click="mode = 'single'"
          >单任务</button>
          <button
            type="button"
            :class="{ active: mode === 'queue' }"
            :disabled="taskIsActive"
            data-test="queue-mode"
            @click="mode = 'queue'"
          >长任务</button>
        </div>
        <TaskForm
          v-if="mode === 'single'"
          :disabled="taskIsActive"
          @submit="submitTask"
        />
        <QueueForm v-else :disabled="taskIsActive" @submit="submitQueue" />
        <p v-if="pageError" class="page-error" role="alert">{{ pageError }}</p>
      </section>

      <QueueProgress v-if="queue" :queue="queue" />
      <TaskStatus v-if="task" :task="task" />
      <ValidationRounds v-if="task" :rounds="task.rounds" />
      <ReportPanel
        v-if="task && FINAL_TASK_STATUSES.has(task.status)"
        :task="task"
        :report="report"
        :diff="diff"
        :submitting-review="reviewing"
        @review="submitReview"
      />
      <section
        v-if="queue && (queue.status === 'completed' || queue.status === 'rejected')"
        class="panel report-panel"
        data-test="queue-report"
      >
        <div class="panel-heading compact-heading">
          <div><p class="eyebrow">长任务交付</p><h2>完整队列报告</h2></div>
        </div>
        <pre>{{ queueReport || "报告正在生成。" }}</pre>
        <div class="review-section">
          <h3>最终累计 Diff</h3>
          <p class="hash-copy">SHA-256：<code>{{ queue.cumulative_diff_sha256 || "—" }}</code></p>
          <pre class="diff-view">{{ queueDiff || "（无差异）" }}</pre>
        </div>
      </section>
    </main>

    <footer>
      <span>Codex Orchestrator</span>
      <span>单项目 · 串行任务 · 本机登录</span>
    </footer>
  </div>
</template>
