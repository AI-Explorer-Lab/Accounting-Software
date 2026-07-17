<script setup lang="ts">
import { computed } from "vue";

import type { QueueData, QueueSubtaskStatus } from "../types/task";


const props = defineProps<{ queue: QueueData }>();

const queueLabels: Record<QueueData["status"], string> = {
  pending: "等待启动",
  running: "执行中",
  waiting_review: "等待人工审查",
  rejected: "已驳回",
  infrastructure_error: "运行环境故障",
  completed: "全部完成",
};

const subtaskLabels: Record<QueueSubtaskStatus, string> = {
  pending: "等待前序任务",
  running: "执行中",
  waiting_review: "等待审查",
  completed: "已完成",
  rejected: "已驳回",
  infrastructure_error: "环境故障",
};

const completedCount = computed(
  () => props.queue.subtasks.filter((task) => task.status === "completed").length,
);
</script>

<template>
  <section class="panel queue-panel" data-test="queue-progress">
    <div class="panel-heading">
      <div>
        <p class="eyebrow">长任务进度</p>
        <h2>{{ queue.name }}</h2>
      </div>
      <span class="status-badge" :class="`queue-status-${queue.status}`">
        {{ queueLabels[queue.status] }} · {{ completedCount }}/{{ queue.subtasks.length }}
      </span>
    </div>

    <p class="queue-id">长任务编号：<code>{{ queue.queue_id }}</code></p>
    <ol class="queue-list">
      <li
        v-for="subtask in queue.subtasks"
        :key="subtask.task_id"
        :class="{
          'current-subtask': subtask.task_id === queue.current_task_id,
          'completed-subtask': subtask.status === 'completed',
        }"
      >
        <span class="queue-sequence">{{ subtask.sequence }}</span>
        <div>
          <strong>{{ subtask.requirement }}</strong>
          <small>{{ subtaskLabels[subtask.status] }}</small>
        </div>
        <code>{{ subtask.task_id }}</code>
      </li>
    </ol>

    <div v-if="queue.last_error_summary" class="result-alert error-alert">
      <strong>队列已暂停</strong>
      <p>{{ queue.last_error_summary }}</p>
    </div>
  </section>
</template>
