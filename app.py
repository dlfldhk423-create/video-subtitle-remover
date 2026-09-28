import os
import uuid
import json
import asyncio
from typing import Dict, Any, List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
import cv2
import aiofiles

from processor import (
    extract_frame_at_time,
    get_video_info,
    inpaint_single_frame,
    process_video_subtitles
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

app = FastAPI(title="AI 비디오 자막 삭제 스튜디오")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

# 작업 상태 관리
tasks_status: Dict[str, Dict[str, Any]] = {}
cancel_flags: Dict[str, bool] = {}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    """동영상을 업로드하고 기본 정보와 첫 프레임을 반환합니다."""
    video_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1] or ".mp4"
    saved_filename = f"{video_id}{ext}"
    saved_path = os.path.join(UPLOAD_DIR, saved_filename)

    async with aiofiles.open(saved_path, "wb") as out_file:
        while content := await file.read(1024 * 1024):  # 1MB 씩 스트리밍
            await out_file.write(content)

    # 비디오 메타데이터 확인
    info = get_video_info(saved_path)
    if not info or info.get("total_frames", 0) <= 0:
        os.remove(saved_path)
        raise HTTPException(status_code=400, detail="유효한 비디오 파일이 아니거나 손상되었습니다.")

    # 첫 프레임 추출하여 저장
    frame = extract_frame_at_time(saved_path, 0.0)
    thumb_name = f"{video_id}_thumb.jpg"
    thumb_path = os.path.join(STATIC_DIR, thumb_name)
    if frame is not None:
        cv2.imwrite(thumb_path, frame)

    return JSONResponse({
        "video_id": video_id,
        "filename": file.filename,
        "info": info,
        "thumbnail_url": f"/static/{thumb_name}",
        "video_path": saved_path
    })


@app.post("/api/sample")
async def load_sample_video():
    """테스트용 샘플 영상을 업로드 폴더로 복사하고 바로 에디터를 엽니다."""
    sample_src = os.path.join(BASE_DIR, "sample_subtitle_video.mp4")
    if not os.path.exists(sample_src):
        raise HTTPException(status_code=404, detail="샘플 영상을 찾을 수 없습니다.")

    video_id = str(uuid.uuid4())
    saved_filename = f"{video_id}.mp4"
    saved_path = os.path.join(UPLOAD_DIR, saved_filename)
    shutil.copy(sample_src, saved_path)

    info = get_video_info(saved_path)
    frame = extract_frame_at_time(saved_path, 0.0)
    thumb_name = f"{video_id}_thumb.jpg"
    thumb_path = os.path.join(STATIC_DIR, thumb_name)
    if frame is not None:
        cv2.imwrite(thumb_path, frame)

    return JSONResponse({
        "video_id": video_id,
        "filename": "sample_subtitle_video.mp4",
        "info": info,
        "thumbnail_url": f"/static/{thumb_name}",
        "video_path": saved_path
    })


@app.get("/api/frame")
async def get_frame(video_id: str, time_sec: float = 0.0):
    """비디오의 특정 시간 프레임을 이미지로 반환합니다."""
    # 업로드 디렉터리에서 파일 찾기
    found_files = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(video_id)]
    if not found_files:
        raise HTTPException(status_code=404, detail="비디오를 찾을 수 없습니다.")

    video_path = os.path.join(UPLOAD_DIR, found_files[0])
    frame = extract_frame_at_time(video_path, time_sec)
    if frame is None:
        raise HTTPException(status_code=400, detail="프레임을 추출할 수 없습니다.")

    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return StreamingResponse(iter([buffer.tobytes()]), media_type="image/jpeg")


@app.post("/api/preview")
async def preview_inpaint(
    video_id: str = Form(...),
    time_sec: float = Form(0.0),
    rois_json: str = Form(...),
    mode: str = Form("smart_text"),
    inpaint_radius: int = Form(4),
    method: str = Form("telea"),
    dilation: int = Form(3)
):
    """지정된 영역과 설정으로 자막 제거 결과를 실시간 미리보기합니다."""
    found_files = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(video_id)]
    if not found_files:
        raise HTTPException(status_code=404, detail="비디오를 찾을 수 없습니다.")

    video_path = os.path.join(UPLOAD_DIR, found_files[0])
    frame = extract_frame_at_time(video_path, time_sec)
    if frame is None:
        raise HTTPException(status_code=400, detail="프레임을 추출할 수 없습니다.")

    try:
        rois = json.loads(rois_json)
    except Exception:
        rois = []

    # 인페인팅 적용
    cleaned, mask = inpaint_single_frame(
        frame=frame,
        rois=rois,
        mode=mode,
        inpaint_radius=inpaint_radius,
        method=method,
        dilation=dilation
    )

    # 마스크 시각화 (빨간색 오버레이 표시)
    mask_visual = frame.copy()
    mask_visual[mask > 0] = [0, 0, 255] # 빨간색

    # 결과 이미지를 메모리에서 JPEG 인코딩
    _, cleaned_buf = cv2.imencode('.jpg', cleaned, [cv2.IMWRITE_JPEG_QUALITY, 92])
    _, mask_buf = cv2.imencode('.jpg', mask_visual, [cv2.IMWRITE_JPEG_QUALITY, 90])

    import base64
    return JSONResponse({
        "cleaned_base64": f"data:image/jpeg;base64,{base64.b64encode(cleaned_buf).decode('utf-8')}",
        "mask_base64": f"data:image/jpeg;base64,{base64.b64encode(mask_buf).decode('utf-8')}"
    })


def run_video_task(
    task_id: str,
    input_path: str,
    output_path: str,
    rois: List[Dict[str, int]],
    mode: str,
    inpaint_radius: int,
    method: str,
    dilation: int
):
    def update_progress(data: Dict[str, Any]):
        tasks_status[task_id].update(data)

    def is_cancelled():
        return cancel_flags.get(task_id, False)

    try:
        tasks_status[task_id]["status"] = "processing"
        success = process_video_subtitles(
            input_video_path=input_path,
            output_video_path=output_path,
            rois=rois,
            mode=mode,
            inpaint_radius=inpaint_radius,
            method=method,
            dilation=dilation,
            progress_callback=update_progress,
            cancel_flag=is_cancelled
        )
        if success:
            tasks_status[task_id]["status"] = "completed"
            tasks_status[task_id]["percent"] = 100.0
            tasks_status[task_id]["download_url"] = f"/api/download/{task_id}"
            tasks_status[task_id]["video_url"] = f"/outputs/{os.path.basename(output_path)}"
        else:
            tasks_status[task_id]["status"] = "cancelled"
    except Exception as e:
        tasks_status[task_id]["status"] = "failed"
        tasks_status[task_id]["error"] = str(e)


@app.post("/api/process")
async def start_process(
    background_tasks: BackgroundTasks,
    video_id: str = Form(...),
    rois_json: str = Form(...),
    mode: str = Form("smart_text"),
    inpaint_radius: int = Form(4),
    method: str = Form("telea"),
    dilation: int = Form(3)
):
    """전체 비디오 자막 제거 렌더링 작업을 시작합니다."""
    found_files = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(video_id)]
    if not found_files:
        raise HTTPException(status_code=404, detail="비디오를 찾을 수 없습니다.")

    video_path = os.path.join(UPLOAD_DIR, found_files[0])
    task_id = str(uuid.uuid4())
    output_filename = f"cleaned_{video_id}.mp4"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    try:
        rois = json.loads(rois_json)
    except Exception:
        rois = []

    tasks_status[task_id] = {
        "task_id": task_id,
        "video_id": video_id,
        "percent": 0.0,
        "status": "pending",
        "output_filename": output_filename,
        "fps_speed": 0,
        "eta_seconds": 0
    }
    cancel_flags[task_id] = False

    background_tasks.add_task(
        run_video_task,
        task_id=task_id,
        input_path=video_path,
        output_path=output_path,
        rois=rois,
        mode=mode,
        inpaint_radius=inpaint_radius,
        method=method,
        dilation=dilation
    )

    return JSONResponse({"task_id": task_id})


@app.get("/api/progress/{task_id}")
async def get_progress(task_id: str):
    """작업 진행률을 실시간 조회합니다."""
    if task_id not in tasks_status:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return JSONResponse(tasks_status[task_id])


@app.post("/api/cancel/{task_id}")
async def cancel_task(task_id: str):
    """진행 중인 작업을 취소합니다."""
    if task_id in cancel_flags:
        cancel_flags[task_id] = True
        if task_id in tasks_status:
            tasks_status[task_id]["status"] = "cancelling"
    return JSONResponse({"status": "cancelled"})


@app.get("/api/download/{task_id}")
async def download_result(task_id: str):
    """완성된 비디오를 다운로드합니다."""
    if task_id not in tasks_status:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    task = tasks_status[task_id]
    if task.get("status") != "completed":
        raise HTTPException(status_code=400, detail="비디오 처리가 아직 완료되지 않았습니다.")

    output_filename = task.get("output_filename")
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    if not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="결과 파일을 찾을 수 없습니다.")

    return FileResponse(
        path=output_path,
        filename=f"subtitle_removed_{output_filename}",
        media_type="video/mp4"
    )
