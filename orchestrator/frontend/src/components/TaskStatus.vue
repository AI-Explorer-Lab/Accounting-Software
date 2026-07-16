<script setup lang="ts">
import { computed } from "vue";

import type { TaskData } from "../types/task";


const props = defineProps<{
  task: TaskData;
}>();

const labels: Record<TaskData["status"], string> = {
  accepted: "已接收",
  running: "执行中",
  success: "机器验证通过",
  manual_review: "机器流程待处理",
  infrastructure_error: "运行环境故障",
};

const reviewLabels: Record<TaskData["review_status"], string> = {
  pending: "待人工审查",
  approved: "已批准",
  changes_requested: "要求修改",
  rejected: "已驳回",
  unavailable: "旧记录无审查信息",
};

const statusLabel = computed(() => labels[props.task.status]);
const reviewLabel = computed(() => reviewLabels[props.task.review_status]);
const effectivePermissions = computed(() => {
  const effective = props.task.permissions.effective;
  return typeof effective === "object" && effective !== null
    ? (effective as Record<string, unknown>)
    : {};
});

function formatTime(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}
</script>

<template>
  <section class="panel status-panel" data-test="task-status">
    <div class="panel-heading">
      <div>
        <p class="eyebrow">当前任务</p>
        <h2>{{ task.requirement }}</h2>
      </div>
      <span class="status-badge" :class="`status-${task.status}`">
        {{ statusLabel }}
      </span>
    </div>

    <dl class="status-grid">
      <div>
        <dt>任务编号</dt>
        <dd>{{ task.task_id }}</dd>
      </div>
      <div>
        <dt>当前阶段</dt>
        <dd>{{ task.phase || "等待启动" }}</dd>
      </div>
      <div>
        <dt>Codex 轮次</dt>
        <dd>{{ task.turn_count }}</dd>
      </div>
      <div>
        <dt>验证失败</dt>
        <dd>{{ task.failure_count }} / 3</dd>
      </div>
      <div>
        <dt>Thread</dt>
        <dd>{{ task.thread_id || "尚未创建" }}</dd>
      </div>
      <div>
        <dt>更新时间</dt>
        <dd>{{ formatTime(task.updated_at) }}</dd>
      </div>
      <div>
        <dt>人工审查</dt>
        <dd>{{ reviewLabel }}</dd>
      </div>
      <div v-if="!task.legacy">
        <dt>任务分支</dt>
        <dd>{{ task.workspace.task_branch || "—" }}</dd>
      </div>
      <div v-if="!task.legacy">
        <dt>基线 commit</dt>
        <dd>{{ task.workspace.base_commit || "—" }}</dd>
      </div>
      <div v-if="!task.legacy">
        <dt>独立 worktree</dt>
        <dd>{{ task.workspace.worktree || "—" }}</dd>
      </div>
      <div v-if="!task.legacy">
        <dt>权限核验</dt>
        <dd>{{ effectivePermissions.verified ? "已通过" : "未通过" }}</dd>
      </div>
      <div v-if="!task.legacy">
        <dt>网络</dt>
        <dd>{{ effectivePermissions.network || "disabled" }}</dd>
      </div>
      <div v-if="!task.legacy">
        <dt>越权拒绝</dt>
        <dd>{{ task.audit_summary.denied_event_count || 0 }} 次</dd>
      </div>
    </dl>

    <div v-if="task.history_warning" class="result-alert review-alert">
      <strong>历史记录不完整</strong>
      <p>{{ task.history_warning }}</p>
    </div>

    <div v-if="task.infrastructure_error" class="result-alert error-alert">
      <strong>运行环境故障</strong>
      <p>{{ task.infrastructure_error }}</p>
    </div>
    <div
      v-else-if="task.status === 'manual_review'"
      class="result-alert review-alert"
    >
      <strong>机器流程需要人工判断</strong>
      <p>{{ task.last_error_summary || "代码已连续三轮验证失败。" }}</p>
    </div>
  </section>
</template>
