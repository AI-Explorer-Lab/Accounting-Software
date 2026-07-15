"""Render Codex prompts and persist complete human/machine final reports."""

from __future__ import annotations

from pathlib import Path
import re
import shlex
from typing import Mapping

from .models import RunResult, RunState, TaskSpec, ValidationRound
from .state import StateStore, redact_sensitive_text, sanitize_for_codex


_PLACEHOLDER = re.compile(r"\{\{([a-z_][a-z0-9_]*)\}\}")


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) or "- 无"


def _indented(text: str) -> str:
    if not text.strip():
        return "    （无）"
    return "\n".join(f"    {line}" for line in text.splitlines())


class TemplateRenderer:
    """Strict renderer for the three version-controlled Markdown templates."""

    ALLOWED_TEMPLATES = {
        "initial_prompt.md",
        "repair_prompt.md",
        "final_report.md",
    }

    def __init__(self, template_dir: str | Path | None = None) -> None:
        self.template_dir = (
            Path(template_dir)
            if template_dir is not None
            else Path(__file__).with_name("templates")
        )

    def render(self, template_name: str, values: Mapping[str, object]) -> str:
        if template_name not in self.ALLOWED_TEMPLATES:
            raise ValueError(f"unsupported template: {template_name}")
        template = (self.template_dir / template_name).read_text(encoding="utf-8")
        missing = sorted(set(_PLACEHOLDER.findall(template)) - set(values))
        if missing:
            raise ValueError(f"missing template values: {', '.join(missing)}")
        rendered = _PLACEHOLDER.sub(
            lambda match: str(values[match.group(1)]), template
        )
        return redact_sensitive_text(rendered)


class PromptRenderer:
    """Build the initial and repair messages sent to the same Codex thread."""

    def __init__(
        self,
        renderer: TemplateRenderer | None = None,
        *,
        repair_summary_limit: int = 8_000,
    ) -> None:
        self.renderer = renderer or TemplateRenderer()
        self.repair_summary_limit = repair_summary_limit

    def initial_prompt(self, task: TaskSpec, repo_root: str | Path) -> str:
        return self.renderer.render(
            "initial_prompt.md",
            {
                "task_id": task.task_id,
                "repo_root": str(Path(repo_root).resolve()),
                "requirement": task.requirement,
                "acceptance_criteria": _bullets(task.acceptance_criteria),
            },
        )

    def repair_prompt(
        self,
        task: TaskSpec,
        state: RunState,
        validation_round: ValidationRound,
    ) -> str:
        details = self._failure_details(validation_round)
        return self.renderer.render(
            "repair_prompt.md",
            {
                "task_id": task.task_id,
                "failure_count": state.failure_count,
                "requirement": task.requirement,
                "acceptance_criteria": _bullets(task.acceptance_criteria),
                "failure_details": sanitize_for_codex(
                    details, self.repair_summary_limit
                ),
            },
        )

    @staticmethod
    def _failure_details(validation_round: ValidationRound) -> str:
        parts: list[str] = []
        if validation_round.failure_summary:
            parts.append(validation_round.failure_summary)
        if validation_round.infrastructure_error:
            parts.append(f"基础设施错误：{validation_round.infrastructure_error}")
        for index, result in enumerate(validation_round.failed_results, start=1):
            output = result.stderr.strip() or result.stdout.strip() or "（无输出）"
            parts.extend(
                [
                    f"### 失败命令 {index}",
                    f"- 阶段：{result.stage or validation_round.stage}",
                    f"- 命令：`{shlex.join(result.command)}`",
                    f"- 退出码：{result.exit_code}",
                    f"- 超时：{'是' if result.timed_out else '否'}",
                    f"- 本地日志：{result.log_path or '尚未写入'}",
                    "- 错误输出：",
                    output,
                ]
            )
        return "\n".join(parts) or "验证未通过，但没有可用的错误输出。"


class ReportBuilder:
    """Create and persist the final ``result.json`` and ``report.md`` pair."""

    def __init__(self, renderer: TemplateRenderer | None = None) -> None:
        self.renderer = renderer or TemplateRenderer()

    def build(self, task: TaskSpec, state: RunState) -> tuple[RunResult, str]:
        result = RunResult.from_run(task, state)
        report = self.render(result)
        return result, report

    def persist(
        self, store: StateStore, task: TaskSpec, state: RunState
    ) -> tuple[Path, Path]:
        result, report = self.build(task, state)
        return store.save_result(result), store.save_report(task.task_id, report)

    def render(self, result: RunResult) -> str:
        values = {
            "task_id": result.task_id,
            "status": result.status.value,
            "thread_id": result.thread_id or "未创建",
            "turn_count": result.turn_count,
            "failure_count": result.failure_count,
            "started_at": result.started_at or "未知",
            "finished_at": result.finished_at,
            "requirement": result.requirement,
            "acceptance_criteria": _bullets(result.acceptance_criteria),
            "rounds": self._rounds(result),
            "failures": self._failures(result),
            "logs": _bullets(result.log_paths),
            "baseline_git_status": _indented(result.baseline_git_status),
            "final_git_summary": _indented(result.final_git_summary),
        }
        return self.renderer.render("final_report.md", values)

    @staticmethod
    def _rounds(result: RunResult) -> str:
        if not result.rounds:
            return "尚未执行验证。"
        sections: list[str] = []
        for validation_round in result.rounds:
            sections.append(
                f"### 第 {validation_round.round_number} 轮 — "
                f"{'通过' if validation_round.passed else '失败'}"
            )
            sections.append(f"- 结束阶段：{validation_round.stage}")
            sections.append(
                f"- 时间：{validation_round.started_at} → "
                f"{validation_round.finished_at or '未完成'}"
            )
            command_results = validation_round.command_results
            if not command_results:
                sections.append("- 命令：无")
                continue
            for command in command_results:
                outcome = "通过" if command.passed else "失败"
                sections.append(
                    f"- `{shlex.join(command.command)}`：{outcome}，"
                    f"退出码 {command.exit_code}，耗时 "
                    f"{command.duration_seconds:.3f}s，日志 "
                    f"`{command.log_path or '未写入'}`"
                )
        return "\n".join(sections)

    @staticmethod
    def _failures(result: RunResult) -> str:
        items: list[str] = []
        if result.infrastructure_error:
            items.append(f"- 基础设施故障：{result.infrastructure_error}")
        for validation_round in result.rounds:
            if validation_round.passed:
                continue
            summary = validation_round.failure_summary.strip() or "验证未通过"
            items.append(f"- 第 {validation_round.round_number} 轮：{summary}")
            for command in validation_round.failed_results:
                items.append(
                    f"  - `{shlex.join(command.command)}`，退出码 "
                    f"{command.exit_code}，日志 `{command.log_path or '未写入'}`"
                )
        return "\n".join(items) or "无。"


def render_initial_prompt(task: TaskSpec, repo_root: str | Path) -> str:
    return PromptRenderer().initial_prompt(task, repo_root)


def render_repair_prompt(
    task: TaskSpec,
    state: RunState,
    validation_round: ValidationRound,
    *,
    max_chars: int = 8_000,
) -> str:
    return PromptRenderer(repair_summary_limit=max_chars).repair_prompt(
        task, state, validation_round
    )


__all__ = [
    "PromptRenderer",
    "ReportBuilder",
    "TemplateRenderer",
    "render_initial_prompt",
    "render_repair_prompt",
]
