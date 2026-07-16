from fastapi import APIRouter, Request, status
from fastapi.responses import PlainTextResponse

from ..domain.req import ReviewRequest, TaskCreateRequest
from ..domain.res import ApiResponse, TaskData
from ..service.task_service import TaskService


router = APIRouter(prefix="/tasks", tags=["tasks"])


def _service(request: Request) -> TaskService:
    return request.app.state.task_service


def _response(request: Request, snapshot) -> ApiResponse[TaskData]:
    return ApiResponse(
        data=TaskData.from_snapshot(snapshot),
        request_id=getattr(request.state, "request_id", None),
    )


@router.post(
    "",
    response_model=ApiResponse[TaskData],
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_task(
    payload: TaskCreateRequest,
    request: Request,
) -> ApiResponse[TaskData]:
    snapshot = _service(request).start_task(
        payload.requirement,
        payload.acceptance_criteria,
    )
    return _response(request, snapshot)


@router.get("/{task_id}", response_model=ApiResponse[TaskData])
async def get_task(task_id: str, request: Request) -> ApiResponse[TaskData]:
    return _response(request, _service(request).get_task(task_id))


@router.post(
    "/{task_id}/resume",
    response_model=ApiResponse[TaskData],
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_task(task_id: str, request: Request) -> ApiResponse[TaskData]:
    return _response(request, _service(request).resume_task(task_id))


@router.get("/{task_id}/report", response_class=PlainTextResponse)
async def get_report(task_id: str, request: Request) -> PlainTextResponse:
    report = _service(request).get_report(task_id)
    return PlainTextResponse(report, media_type="text/markdown; charset=utf-8")


@router.get("/{task_id}/diff", response_class=PlainTextResponse)
async def get_diff(task_id: str, request: Request) -> PlainTextResponse:
    diff = _service(request).get_diff(task_id)
    return PlainTextResponse(diff, media_type="text/x-diff; charset=utf-8")


@router.post("/{task_id}/review", response_model=ApiResponse[TaskData])
async def review_task(
    task_id: str,
    payload: ReviewRequest,
    request: Request,
) -> ApiResponse[TaskData]:
    snapshot = _service(request).review_task(
        task_id,
        decision=payload.decision,
        reviewer=payload.reviewer,
        comment=payload.comment,
        reviewed_diff_sha256=payload.reviewed_diff_sha256,
    )
    return _response(request, snapshot)
