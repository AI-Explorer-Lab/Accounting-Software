import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  createTask: vi.fn(),
  getTask: vi.fn(),
  getTaskDiff: vi.fn(),
  getTaskReport: vi.fn(),
  submitTaskReview: vi.fn(),
}));

vi.mock("../src/api/tasks", () => api);

import App from "../src/App.vue";
import type { TaskData } from "../src/types/task";


function task(
  status: TaskData["status"],
  overrides: Partial<TaskData> = {},
): TaskData {
  return {
    task_id: "task-1",
    requirement: "Add filtering",
    acceptance_criteria: ["Filtering works"],
    status,
    schema_version: 1,
    legacy: false,
    history_warning: null,
    machine_status: status,
    review_status: "pending",
    phase: status === "running" ? "validating" : "completed",
    thread_id: "thread-1",
    turn_count: 1,
    failure_count: 0,
    rounds: [],
    last_error_summary: "",
    infrastructure_error: null,
    started_at: "2026-07-15T08:00:00+08:00",
    updated_at: "2026-07-15T08:00:01+08:00",
    finished_at: status === "success" ? "2026-07-15T08:00:02+08:00" : null,
    report_url: status === "success" ? "/api/tasks/task-1/report" : null,
    diff_url: status === "success" ? "/api/tasks/task-1/diff" : null,
    workspace: {
      base_commit: "a".repeat(40),
      task_branch: "codex/task-1",
      worktree: ".codex-orchestrator/worktrees/task-1",
    },
    permissions: { effective: { verified: true, network: "disabled" } },
    audit_summary: { event_count: 12, denied_event_count: 0 },
    changed_files: [],
    codex_responses: [{ turn_number: 1, response: "Implemented." }],
    final_diff_sha256: "b".repeat(64),
    diff_redaction_count: 0,
    review: null,
    ...overrides,
  };
}


describe("App", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    localStorage.clear();
    api.createTask.mockReset();
    api.getTask.mockReset();
    api.getTaskDiff.mockReset();
    api.getTaskReport.mockReset();
    api.submitTaskReview.mockReset();
    api.getTaskDiff.mockResolvedValue("diff --git a/file b/file");
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("submits a task, polls until completion, and displays the report", async () => {
    api.createTask.mockResolvedValue(task("accepted"));
    api.getTask.mockResolvedValue(task("success"));
    api.getTaskReport.mockResolvedValue("# Final report");
    const wrapper = mount(App);

    await wrapper.get('[data-test="requirement"]').setValue("Add filtering");
    await wrapper.get('[data-test="criterion-0"]').setValue("Filtering works");
    await wrapper.get('[data-test="task-form"]').trigger("submit");
    await flushPromises();

    expect(api.createTask).toHaveBeenCalledWith({
      requirement: "Add filtering",
      acceptance_criteria: ["Filtering works"],
    });
    expect(localStorage.getItem("codex-orchestrator:last-task-id")).toBe("task-1");
    expect(wrapper.get('[data-test="task-status"]').text()).toContain("已接收");
    expect(wrapper.get('[data-test="submit"]').attributes("disabled")).toBeDefined();

    await vi.advanceTimersByTimeAsync(2_000);
    await flushPromises();

    expect(api.getTask).toHaveBeenCalledWith("task-1");
    expect(api.getTaskReport).toHaveBeenCalledWith("task-1");
    expect(wrapper.get('[data-test="task-status"]').text()).toContain("机器验证通过");
    expect(wrapper.get('[data-test="report-panel"]').text()).toContain(
      "# Final report",
    );

    const completedPollCount = api.getTask.mock.calls.length;
    await vi.advanceTimersByTimeAsync(4_000);
    expect(api.getTask).toHaveBeenCalledTimes(completedPollCount);
    wrapper.unmount();
  });

  it("restores the most recent task after a page refresh", async () => {
    localStorage.setItem("codex-orchestrator:last-task-id", "task-1");
    api.getTask.mockResolvedValue(task("success"));
    api.getTaskReport.mockResolvedValue("# Restored report");

    const wrapper = mount(App);
    await flushPromises();

    expect(api.getTask).toHaveBeenCalledWith("task-1");
    expect(wrapper.get('[data-test="report-panel"]').text()).toContain(
      "# Restored report",
    );
    wrapper.unmount();
  });

  it("submits an immutable review bound to the displayed diff", async () => {
    localStorage.setItem("codex-orchestrator:last-task-id", "task-1");
    api.getTask.mockResolvedValue(task("success"));
    api.getTaskReport.mockResolvedValue("# Report");
    api.submitTaskReview.mockResolvedValue(
      task("success", {
        review_status: "approved",
        review: {
          decision: "approved",
          reviewer: "Local Reviewer",
          comment: "Checked.",
          reviewed_diff_sha256: "b".repeat(64),
        },
      }),
    );
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.get('[data-test="reviewer"]').setValue("Local Reviewer");
    await wrapper.get('[data-test="review-comment"]').setValue("Checked.");
    await wrapper.get('[data-test="approve"]').trigger("click");
    await flushPromises();

    expect(api.submitTaskReview).toHaveBeenCalledWith("task-1", {
      decision: "approved",
      reviewer: "Local Reviewer",
      comment: "Checked.",
      reviewed_diff_sha256: "b".repeat(64),
    });
    expect(wrapper.get('[data-test="review-section"]').text()).toContain(
      "Local Reviewer",
    );
    wrapper.unmount();
  });

  it("marks legacy tasks without inventing review or workspace data", async () => {
    localStorage.setItem("codex-orchestrator:last-task-id", "task-1");
    api.getTask.mockResolvedValue(
      task("success", {
        schema_version: 0,
        legacy: true,
        history_warning: "历史记录不完整。",
        review_status: "unavailable",
        workspace: {},
        permissions: {},
        diff_url: null,
      }),
    );
    api.getTaskReport.mockResolvedValue("# Old report");
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.get('[data-test="task-status"]').text()).toContain(
      "历史记录不完整",
    );
    expect(wrapper.find('[data-test="review-section"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it.each([
    {
      status: "manual_review" as const,
      label: "机器流程待处理",
      overrides: { last_error_summary: "Three validation rounds failed" },
    },
    {
      status: "infrastructure_error" as const,
      label: "运行环境故障",
      overrides: { infrastructure_error: "Codex runtime unavailable" },
    },
  ])("displays the $status result separately", async ({ status, label, overrides }) => {
    localStorage.setItem("codex-orchestrator:last-task-id", "task-1");
    api.getTask.mockResolvedValue(
      task(status, {
        ...overrides,
        finished_at: "2026-07-15T08:00:02+08:00",
        report_url: "/api/tasks/task-1/report",
      }),
    );
    api.getTaskReport.mockResolvedValue("# Result report");

    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.get('[data-test="task-status"]').text()).toContain(label);
    expect(wrapper.get('[data-test="report-panel"]').text()).toContain(
      "# Result report",
    );
    wrapper.unmount();
  });
});
