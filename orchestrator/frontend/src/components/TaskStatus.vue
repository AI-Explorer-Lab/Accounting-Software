<script setup lang="ts">
import { computed } from "vue";

import type { TaskData } from "../types/task";


const props = defineProps<{
  task: TaskData;
}>();

const labels: Record<TaskData["status"], string> = {
  accepted: "已接收",
  running: "执行中",
  success: "全部通过",
  manual_review: "等待人工审核",
  infrastructure_error: "运行环境故障",
};

const statusLabel = computed(() => labels[props.task.status]);

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
    </dl>

    <div v-if="task.infrastructure_error" class="result-alert error-alert">
      <strong>运行环境故障</strong>
      <p>{{ task.infrastructure_error }}</p>
    </div>
    <div
      v-else-if="task.status === 'manual_review'"
      class="result-alert review-alert"
    >
      <strong>需要人工审核</strong>
      <p>{{ task.last_error_summary || "代码已连续三轮验证失败。" }}</p>
    </div>
  </section>
</template>
