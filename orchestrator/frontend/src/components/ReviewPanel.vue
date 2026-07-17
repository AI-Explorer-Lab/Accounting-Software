<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";

import type { ReviewDecision, TaskData } from "../types/task";

const props = defineProps<{ task: TaskData; submitting: boolean }>();
const emit = defineEmits<{
  review: [payload: { decision: ReviewDecision; reviewer: string; comment: string }];
}>();

const reviewer = ref("");
const comment = ref("");
const formError = ref("");
const pendingDecision = ref<ReviewDecision | null>(null);
const confirmButton = ref<HTMLButtonElement | null>(null);
const decisionLabels: Record<ReviewDecision, string> = {
  approved: "批准变更",
  changes_requested: "要求修改",
  rejected: "驳回任务",
};
const existingReview = computed(() => props.task.review as Record<string, unknown> | null);
const impactCopy = computed(() => {
  if (!pendingDecision.value) return "";
  if (!props.task.queue_id) {
    return pendingDecision.value === "changes_requested"
      ? "任务会从当前 Thread 继续修改，原审核记录保持不变。"
      : "结论会绑定当前 Diff 指纹并写入不可变审核历史。";
  }
  const labels: Record<ReviewDecision, string> = {
    approved: "当前子任务将完成，队列会继续执行下一个尚未开始的子任务。",
    changes_requested: "当前子任务会从同一 Thread 继续修改，队列暂不前进。",
    rejected: "整个长任务将停止，后续子任务不会自动执行。",
  };
  return labels[pendingDecision.value];
});

function prepare(decision: ReviewDecision): void {
  if (!reviewer.value.trim()) {
    formError.value = "请填写审核人。";
    return;
  }
  formError.value = "";
  pendingDecision.value = decision;
}

function confirm(): void {
  if (!pendingDecision.value) return;
  emit("review", {
    decision: pendingDecision.value,
    reviewer: reviewer.value.trim(),
    comment: comment.value.trim(),
  });
  pendingDecision.value = null;
}

function display(value: unknown): string {
  return value === null || value === undefined || value === "" ? "—" : String(value);
}

watch(pendingDecision, async (value) => {
  if (!value) return;
  await nextTick();
  confirmButton.value?.focus();
});
</script>

<template>
  <section class="surface review-surface" data-test="review-panel">
    <div class="surface-heading">
      <div><span class="section-kicker">人工关口</span><h2>提交审核结论</h2></div>
      <span class="hash-chip">SHA {{ task.final_diff_sha256.slice(0, 10) || "—" }}</span>
    </div>

    <div v-if="task.diff_redaction_count > 0" class="callout danger-callout">
      <strong>暂时不能提交审核</strong>
      <p>Diff 中有 {{ task.diff_redaction_count }} 处疑似敏感信息已被替换，请先移除后重新运行。</p>
    </div>

    <dl v-if="existingReview && task.review_status !== 'pending'" class="review-result">
      <div><dt>结论</dt><dd>{{ display(existingReview.decision) }}</dd></div>
      <div><dt>审核人</dt><dd>{{ display(existingReview.reviewer) }}</dd></div>
      <div><dt>说明</dt><dd>{{ display(existingReview.comment) }}</dd></div>
      <div><dt>对应 Diff</dt><dd><code>{{ display(existingReview.reviewed_diff_sha256) }}</code></dd></div>
    </dl>

    <form v-else class="review-form" @submit.prevent>
      <label>审核人（本地声明身份）<input v-model="reviewer" data-test="reviewer" :disabled="submitting" /></label>
      <label>审核说明<textarea v-model="comment" data-test="review-comment" rows="4" :disabled="submitting" placeholder="记录判断依据，方便之后回看。" /></label>
      <p v-if="formError" class="form-error" role="alert">{{ formError }}</p>
      <div class="review-actions">
        <button class="primary-button" type="button" data-test="approve" :disabled="submitting || task.diff_redaction_count > 0" @click="prepare('approved')">批准</button>
        <button class="secondary-button" type="button" :disabled="submitting || task.diff_redaction_count > 0" @click="prepare('changes_requested')">要求修改</button>
        <button class="secondary-button danger-button" type="button" :disabled="submitting || task.diff_redaction_count > 0" @click="prepare('rejected')">驳回</button>
      </div>
    </form>

    <div v-if="task.review_history.length" class="review-history">
      <h3>审核历史</h3>
      <ol>
        <li v-for="(item, index) in task.review_history" :key="index">
          <strong>第 {{ item.review_number || index + 1 }} 次 · {{ display(item.decision) }}</strong>
          <span>{{ display(item.reviewer) }} · {{ display(item.comment) }}</span>
        </li>
      </ol>
    </div>

    <div v-if="pendingDecision" class="dialog-backdrop" @click.self="pendingDecision = null" @keydown.esc="pendingDecision = null">
      <div class="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="review-confirm-title" tabindex="-1">
        <span class="dialog-icon">✓</span>
        <h3 id="review-confirm-title">确认{{ decisionLabels[pendingDecision] }}？</h3>
        <p>{{ impactCopy }}</p>
        <div class="dialog-actions">
          <button class="secondary-button" type="button" @click="pendingDecision = null">返回检查</button>
          <button ref="confirmButton" class="primary-button" data-test="confirm-review" type="button" @click="confirm">确认提交</button>
        </div>
      </div>
    </div>
  </section>
</template>
