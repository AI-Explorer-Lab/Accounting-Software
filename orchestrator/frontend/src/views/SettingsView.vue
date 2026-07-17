<script setup lang="ts">
import { computed, ref } from "vue";

import { useOrchestrator } from "../composables/useOrchestrator";

const store = useOrchestrator();
const saving = ref(false);
const browserPermission = ref(
  typeof Notification === "undefined" ? "unsupported" : Notification.permission,
);
const settings = computed(() => store.notificationSettings.value);

async function save(inApp: boolean, browser: boolean): Promise<void> {
  saving.value = true;
  await store.updateNotificationPreferences(inApp, browser);
  saving.value = false;
}

async function toggleBrowser(): Promise<void> {
  if (settings.value.browser && browserPermission.value === "granted") {
    await save(settings.value.in_app, false);
    return;
  }
  if (typeof Notification === "undefined") return;
  browserPermission.value = await Notification.requestPermission();
  if (browserPermission.value === "granted") {
    await save(settings.value.in_app, true);
  }
}
</script>

<template>
  <div class="view-stack settings-view">
    <header class="view-header"><div><span class="section-kicker">本地工作台偏好</span><h1>设置</h1><p>选择需要的提醒入口；外部投递由服务端配置，不影响任务结果。</p></div></header>
    <div class="settings-grid">
      <section class="surface setting-card"><span class="setting-icon">●</span><div><h2>站内通知</h2><p>审核、完成、失败与取消事件会进入右上角通知中心。</p></div><button class="switch" :class="{ 'is-on': settings.in_app }" type="button" role="switch" :aria-checked="settings.in_app" :disabled="saving" @click="save(!settings.in_app, settings.browser)"><i /></button></section>
      <section class="surface setting-card"><span class="setting-icon">◫</span><div><h2>浏览器通知</h2><p>授权后，新事件会通过系统通知提示；首次读取不会补发旧提醒。</p><small v-if="browserPermission === 'denied'">浏览器已拒绝授权，请在浏览器设置中重新开启。</small></div><button class="switch" :class="{ 'is-on': settings.browser && browserPermission === 'granted' }" type="button" role="switch" :aria-checked="settings.browser && browserPermission === 'granted'" :disabled="saving || browserPermission === 'unsupported' || browserPermission === 'denied'" @click="toggleBrowser"><i /></button></section>
      <section class="surface setting-card"><span class="setting-icon">@</span><div><h2>邮件投递</h2><p>SMTP 投递失败只记录在通知中，不会改变任务状态。</p><code>backend/config/app.yaml</code></div><span class="configuration-state" :class="{ configured: settings.email_configured }">{{ settings.email_configured ? "已配置" : "未配置" }}</span></section>
      <section class="surface setting-card"><span class="setting-icon">↗</span><div><h2>Webhook</h2><p>向内部自动化入口发送结构化通知，超时或失败不会阻塞执行。</p><code>notifications.webhook_url</code></div><span class="configuration-state" :class="{ configured: settings.webhook_configured }">{{ settings.webhook_configured ? "已配置" : "未配置" }}</span></section>
    </div>
  </div>
</template>
