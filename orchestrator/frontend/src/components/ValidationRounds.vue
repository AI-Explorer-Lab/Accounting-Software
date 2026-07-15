<script setup lang="ts">
import type { ValidationRound } from "../types/task";


defineProps<{
  rounds: ValidationRound[];
}>();
</script>

<template>
  <section v-if="rounds.length" class="panel" data-test="validation-rounds">
    <div class="panel-heading compact-heading">
      <div>
        <p class="eyebrow">验证过程</p>
        <h2>测试轮次</h2>
      </div>
    </div>

    <div class="round-list">
      <article
        v-for="round in rounds"
        :key="round.round_number"
        class="round-card"
      >
        <div class="round-title">
          <strong>第 {{ round.round_number }} 轮</strong>
          <span :class="round.passed ? 'pass-text' : 'fail-text'">
            {{ round.passed ? "通过" : "失败" }}
          </span>
        </div>
        <p v-if="round.failure_summary" class="round-summary">
          {{ round.failure_summary }}
        </p>
        <ul class="command-list">
          <li v-for="(command, index) in round.commands" :key="index">
            <span :class="command.passed ? 'command-pass' : 'command-fail'" />
            <code>{{ command.command.join(" ") }}</code>
            <span>{{ command.duration_seconds.toFixed(2) }}s</span>
          </li>
        </ul>
      </article>
    </div>
  </section>
</template>
