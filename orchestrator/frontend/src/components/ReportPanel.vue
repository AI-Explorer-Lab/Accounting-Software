<script setup lang="ts">
import { ref } from "vue";

import type { ReviewDecision, TaskData } from "../types/task";


const props = defineProps<{
  task: TaskData;
  report: string;
  diff: string;
  submittingReview: boolean;
}>();

const emit = defineEmits<{
  review: [payload: { decision: ReviewDecision; reviewer: string; comment: string }];
}>();

const reviewer = ref("");
const comment = ref("");
const formError = ref("");

function display(value: unknown): string {
  return value === null || value === undefined || value === "" ? "—" : String(value);
}

function submit(decision: ReviewDecision): void {
  const normalizedReviewer = reviewer.value.trim();
  if (!normalizedReviewer) {
    formError.value = "请填写审查人。";
    return;
  }
  formError.value = "";
  emit("review", {
    decision,
    reviewer: normalizedReviewer,
    comment: comment.value.trim(),
  });
}
</script>

<template>
  <section class="panel report-panel" data-test="report-panel">
    <div class="panel-heading compact-heading">
      <div>
        <p class="eyebrow">运行记录与人工验收</p>
        <h2>检查这一次任务</h2>
      </div>
    </div>

    <template v-if="!task.legacy">
      <div class="review-section">
        <h3>Codex 可见回复</h3>
        <p v-if="task.codex_responses.length === 0" class="empty-copy">没有可见回复。</p>
        <article
          v-for="response in task.codex_responses"
          :key="response.turn_number"
          class="response-card"
        >
          <strong>第 {{ response.turn_number }} 轮</strong>
          <pre>{{ response.response }}</pre>
        </article>
      </div>

      <div class="review-section">
        <h3>变更文件</h3>
        <p v-if="task.changed_files.length === 0" class="empty-copy">没有文件变更。</p>
        <div v-else class="change-list">
          <div v-for="file in task.changed_files" :key="String(file.path)">
            <code>{{ display(file.path) }}</code>
            <span>{{ display(file.status) }}</span>
            <span>+{{ display(file.additions) }} / -{{ display(file.deletions) }}</span>
          </div>
        </div>
      </div>

      <div class="review-section">
        <h3>最终 Diff</h3>
        <p class="hash-copy">SHA-256：<code>{{ task.final_diff_sha256 || "—" }}</code></p>
        <div v-if="task.diff_redaction_count > 0" class="result-alert error-alert">
          <strong>不能提交审查</strong>
          <p>Diff 中发现并替换了 {{ task.diff_redaction_count }} 处疑似敏感信息，请先创建新任务移除它。</p>
        </div>
        <pre class="diff-view">{{ diff || "（无差异）" }}</pre>
      </div>

      <div class="review-section" data-test="review-section">
        <h3>人工审查结论</h3>
        <dl v-if="task.review" class="review-result">
          <div><dt>结论</dt><dd>{{ display(task.review.decision) }}</dd></div>
          <div><dt>审查人</dt><dd>{{ display(task.review.reviewer) }}</dd></div>
          <div><dt>说明</dt><dd>{{ display(task.review.comment) }}</dd></div>
          <div><dt>对应 Diff</dt><dd><code>{{ display(task.review.reviewed_diff_sha256) }}</code></dd></div>
        </dl>
        <form v-else-if="task.review_status === 'pending'" class="review-form" @submit.prevent>
          <label>
            审查人（本地声明身份）
            <input v-model="reviewer" data-test="reviewer" :disabled="submittingReview" />
          </label>
          <label>
            说明
            <textarea v-model="comment" data-test="review-comment" :disabled="submittingReview" />
          </label>
          <p v-if="formError" class="form-error" role="alert">{{ formError }}</p>
          <div class="review-actions">
            <button
              type="button"
              class="primary-button"
              data-test="approve"
              :disabled="submittingReview || task.diff_redaction_count > 0"
              @click="submit('approved')"
            >批准</button>
            <button
              type="button"
              class="secondary-button"
              :disabled="submittingReview || task.diff_redaction_count > 0"
              @click="submit('changes_requested')"
            >要求修改</button>
            <button
              type="button"
              class="secondary-button danger-button"
              :disabled="submittingReview || task.diff_redaction_count > 0"
              @click="submit('rejected')"
            >驳回</button>
          </div>
        </form>
      </div>
    </template>

    <div v-if="report" class="review-section">
      <h3>汇总报告</h3>
      <pre>{{ report }}</pre>
    </div>
  </section>
</template>
