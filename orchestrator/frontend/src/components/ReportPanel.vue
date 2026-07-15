<script setup lang="ts">
defineProps<{
  report: string;
}>();
</script>

<template>
  <section v-if="report" class="panel report-panel" data-test="report-panel">
    <div class="panel-heading compact-heading">
      <div>
        <p class="eyebrow">最终结果</p>
        <h2>人工报告</h2>
      </div>
    </div>
    <pre>{{ report }}</pre>
  </section>
</template>
