<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";

import QueueForm from "../components/QueueForm.vue";
import TaskForm from "../components/TaskForm.vue";
import { useOrchestrator } from "../composables/useOrchestrator";
import type { QueueCreatePayload, TaskCreatePayload } from "../types/task";

const store = useOrchestrator();
const router = useRouter();
const mode = ref<"task" | "queue">("task");
const disabled = computed(() => store.submitting.value || store.isRunning.value);

async function submitTask(payload: TaskCreatePayload): Promise<void> {
  if (await store.submitTask(payload)) await router.push("/monitor");
}

async function submitQueue(payload: QueueCreatePayload): Promise<void> {
  if (await store.submitQueue(payload)) await router.push("/monitor");
}
</script>

<template>
  <div class="view-stack create-view">
    <header class="view-header">
      <div>
        <span class="section-kicker">开始一次受控执行</span>
        <h1>创建任务</h1>
        <p>把需求与验收标准写清楚，Codex 会在隔离工作区中执行并留下完整记录。</p>
      </div>
      <div class="project-context-card">
        <span>当前项目</span>
        <strong>{{ store.activeProject.value?.name || "正在读取" }}</strong>
        <code>{{ store.activeProject.value?.repo_root || "—" }}</code>
      </div>
    </header>

    <div class="create-layout">
      <section class="surface form-surface">
        <div class="surface-heading compact-heading">
          <div><span class="section-kicker">任务定义</span><h2>描述要交付的结果</h2></div>
          <span class="local-chip"><i /> 本机执行</span>
        </div>
        <div class="segmented-control" role="tablist" aria-label="任务类型">
          <button type="button" role="tab" :aria-selected="mode === 'task'" data-test="single-mode" :class="{ active: mode === 'task' }" :disabled="disabled" @click="mode = 'task'">
            单任务<span>一次完整改动</span>
          </button>
          <button type="button" role="tab" :aria-selected="mode === 'queue'" data-test="queue-mode" :class="{ active: mode === 'queue' }" :disabled="disabled" @click="mode = 'queue'">
            长任务<span>人工拆分、依次执行</span>
          </button>
        </div>
        <TaskForm v-if="mode === 'task'" :disabled="disabled" @submit="submitTask" />
        <QueueForm v-else :disabled="disabled" @submit="submitQueue" />
      </section>

      <aside class="create-aside">
        <section class="surface guide-card">
          <span class="guide-index">A</span>
          <h3>先写可观察的结果</h3>
          <p>验收标准越具体，机器验证越能准确判断改动是否完成。</p>
        </section>
        <section class="surface guide-card">
          <span class="guide-index">B</span>
          <h3>长任务由你决定顺序</h3>
          <p>子任务严格串行，并在每一段审核通过后把已批准 Diff 传给下一段。</p>
        </section>
        <section v-if="store.isRunning.value" class="callout warning-callout">
          <strong>当前项目已有执行中的任务</strong>
          <p>可以先去监控页暂停、取消或等待它完成。</p>
          <RouterLink class="inline-link" to="/monitor">打开运行监控 →</RouterLink>
        </section>
      </aside>
    </div>
  </div>
</template>
