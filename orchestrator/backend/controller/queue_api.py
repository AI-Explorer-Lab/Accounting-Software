from fastapi import APIRouter, Request, status
from fastapi.responses import PlainTextResponse

from ..domain.req import QueueCreateRequest
from ..domain.res import ApiResponse, QueueData
from ..service.queue_service import QueueService


router = APIRouter(prefix="/queues", tags=["queues"])


def _service(request: Request) -> QueueService:
    return request.app.state.queue_service


def _response(request: Request, snapshot) -> ApiResponse[QueueData]:
    return ApiResponse(
        data=QueueData.from_snapshot(snapshot),
        request_id=getattr(request.state, "request_id", None),
    )


@router.post(
    "",
    response_model=ApiResponse[QueueData],
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_queue(
    payload: QueueCreateRequest,
    request: Request,
) -> ApiResponse[QueueData]:
    snapshot = _service(request).start_queue(
        payload.name,
        [subtask.model_dump() for subtask in payload.subtasks],
    )
    return _response(request, snapshot)


@router.get("/{queue_id}", response_model=ApiResponse[QueueData])
async def get_queue(queue_id: str, request: Request) -> ApiResponse[QueueData]:
    return _response(request, _service(request).get_queue(queue_id))


@router.post(
    "/{queue_id}/resume",
    response_model=ApiResponse[QueueData],
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_queue(queue_id: str, request: Request) -> ApiResponse[QueueData]:
    return _response(request, _service(request).resume_queue(queue_id))


@router.get("/{queue_id}/report", response_class=PlainTextResponse)
async def get_queue_report(queue_id: str, request: Request) -> PlainTextResponse:
    report = _service(request).get_report(queue_id)
    return PlainTextResponse(report, media_type="text/markdown; charset=utf-8")


@router.get("/{queue_id}/diff", response_class=PlainTextResponse)
async def get_queue_diff(queue_id: str, request: Request) -> PlainTextResponse:
    diff = _service(request).get_diff(queue_id)
    return PlainTextResponse(diff, media_type="text/x-diff; charset=utf-8")
