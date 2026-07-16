<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";

import {
  createTask,
  getTask,
  getTaskDiff,
  getTaskReport,
  submitTaskReview,
} from "./api/tasks";
import ReportPanel from "./components/ReportPanel.vue";
import TaskForm from "./components/TaskForm.vue";
import TaskStatus from "./components/TaskStatus.vue";
import ValidationRounds from "./components/ValidationRounds.vue";
import type {
  ReviewDecision,
  TaskCreatePayload,
  TaskData,
} from "./types/task";


const STORAGE_KEY = "codex-orchestrator:last-task-id";
const POLL_INTERVAL_MS = 2_000;
const FINAL_STATUSES = new Set<TaskData["status"]>([
  "success",
  "manual_review",
  "infrastructure_error",
]);

const task = ref<TaskData | null>(null);
const report = ref("");
const diff = ref("");
const submitting = ref(false);
const reviewing = ref(false);
const pageError = ref("");
let pollTimer: ReturnType<typeof setTimeout> | null = null;

const taskIsActive = computed(
  () =>
    submitting.value ||
    task.value?.status === "accepted" ||
    task.value?.status === "running",
);

function clearPollTimer(): void {
  if (pollTimer !== null) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function schedulePoll(taskId: string): void {
  clearPollTimer();
  pollTimer = setTimeout(() => void refreshTask(taskId), POLL_INTERVAL_MS);
}

async function loadReport(taskId: string): Promise<void> {
  try {
    report.value = await getTaskReport(taskId);
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : "报告读取失败。";
  }
}

async function loadDiff(taskId: string): Promise<void> {
  if (!task.value?.diff_url) {
    diff.value = "";
    return;
  }
  try {
    diff.value = await getTaskDiff(taskId);
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : "Diff 读取失败。";
  }
}

async function refreshTask(taskId: string): Promise<void> {
  try {
    const latest = await getTask(taskId);
    task.value = latest;
    pageError.value = "";
    if (FINAL_STATUSES.has(latest.status)) {
      clearPollTimer();
      await Promise.all([loadReport(taskId), loadDiff(taskId)]);
      return;
    }
    schedulePoll(taskId);
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : "任务状态读取失败。";
    schedulePoll(taskId);
  }
}

async function submitTask(payload: TaskCreatePayload): Promise<void> {
  submitting.value = true;
  pageError.value = "";
  report.value = "";
  diff.value = "";
  clearPollTimer();
  try {
    const accepted = await createTask(payload);
    task.value = accepted;
    localStorage.setItem(STORAGE_KEY, accepted.task_id);
    schedulePoll(accepted.task_id);
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : "任务提交失败。";
  } finally {
    submitting.value = false;
  }
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
    await loadReport(task.value.task_id);
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : "审查提交失败。";
  } finally {
    reviewing.value = false;
  }
}

onMounted(() => {
  const previousTaskId = localStorage.getItem(STORAGE_KEY);
  if (previousTaskId) void refreshTask(previousTaskId);
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
          一次提交一个功能需求。编排器会复用同一个 Codex thread、运行相关测试和全量验证，并在三轮失败后交给人工审核。
        </p>
      </div>
      <div class="hero-mark" aria-hidden="true">
        <span>01</span>
        <div />
        <span>CODEX</span>
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
        <TaskForm :disabled="taskIsActive" @submit="submitTask" />
        <p v-if="pageError" class="page-error" role="alert">
          {{ pageError }}
        </p>
      </section>

      <TaskStatus v-if="task" :task="task" />
      <ValidationRounds v-if="task" :rounds="task.rounds" />
      <ReportPanel
        v-if="task && FINAL_STATUSES.has(task.status)"
        :task="task"
        :report="report"
        :diff="diff"
        :submitting-review="reviewing"
        @review="submitReview"
      />
    </main>

    <footer>
      <span>Codex Orchestrator</span>
      <span>单项目 · 单任务 · 本机登录</span>
    </footer>
  </div>
</template>
