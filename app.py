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
from starlette.responses import Response
import cv2
import aiofiles
import time
import shutil

import db
from processor import (
    extract_frame_at_time,
    get_video_info,
    inpaint_single_frame,
    process_video_subtitles
)

import sys

if getattr(sys, 'frozen', False):
    BUNDLE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    APP_DIR = os.path.dirname(sys.executable)
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = BUNDLE_DIR

UPLOAD_DIR = os.path.join(APP_DIR, "uploads")
OUTPUT_DIR = os.path.join(APP_DIR, "outputs")
STATIC_DIR = os.path.join(BUNDLE_DIR, "static")
TEMPLATES_DIR = os.path.join(BUNDLE_DIR, "templates")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

app = FastAPI(title="AI 비디오 자막 삭제 스튜디오")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

# 관리자 기본 비밀번호
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin1234")

# 작업 상태 관리
tasks_status: Dict[str, Dict[str, Any]] = {}
cancel_flags: Dict[str, bool] = {}


@app.middleware("http")
async def track_visitors_middleware(request: Request, call_next):
    """방문자 접속 정보 자동 로깅"""
    path = request.url.path
    # 정적 리소스는 제외하고 주요 페이지 및 API 요청만 기록
    if not path.startswith(("/static", "/outputs", "/favicon.ico")) and request.method == "GET":
        client_ip = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
        if "," in client_ip:
            client_ip = client_ip.split(",")[0].strip()
        user_agent = request.headers.get("user-agent", "unknown")
        try:
            db.log_visit(ip=client_ip, user_agent=user_agent, path=path)
        except Exception:
            pass

    response = await call_next(request)
    return response


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    """관리자 대시보드 페이지"""
    return templates.TemplateResponse(request=request, name="admin.html")


@app.post("/api/admin/login")
async def admin_login(password: str = Form(...)):
    """관리자 로그인 확인"""
    if password == ADMIN_PASSWORD:
        return JSONResponse({"status": "success", "token": "admin_authenticated"})
    raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다.")


@app.get("/api/admin/stats")
async def admin_stats():
    """관리자 통계 지표 및 로그 조회"""
    stats = db.get_dashboard_stats()
    recent_tasks = db.get_recent_activity(limit=40)
    recent_visitors = db.get_recent_visitors(limit=40)

    # 디스크 사용량 계산
    def get_dir_size_mb(path):
        total = 0
        if os.path.exists(path):
            for dirpath, dirnames, filenames in os.walk(path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if os.path.isfile(fp):
                        total += os.path.getsize(fp)
        return round(total / (1024 * 1024), 2)

    uploads_size = get_dir_size_mb(UPLOAD_DIR)
    outputs_size = get_dir_size_mb(OUTPUT_DIR)

    return JSONResponse({
        "stats": stats,
        "recent_tasks": recent_tasks,
        "recent_visitors": recent_visitors,
        "storage": {
            "uploads_mb": uploads_size,
            "outputs_mb": outputs_size,
            "total_mb": round(uploads_size + outputs_size, 2)
        }
    })


@app.post("/api/admin/clean")
async def admin_clean_storage():
    """임시 업로드 및 출력 파일 정리"""
    cleaned_count = 0
    cleaned_bytes = 0

    for d in [UPLOAD_DIR, OUTPUT_DIR]:
        if os.path.exists(d):
            for f in os.listdir(d):
                if f.startswith(".gitkeep"):
                    continue
                fp = os.path.join(d, f)
                try:
                    if os.path.isfile(fp):
                        cleaned_bytes += os.path.getsize(fp)
                        os.remove(fp)
                        cleaned_count += 1
                except Exception:
                    pass

    return JSONResponse({
        "status": "success",
        "cleaned_files": cleaned_count,
        "cleaned_mb": round(cleaned_bytes / (1024 * 1024), 2)
    })


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
    sample_src = os.path.join(BUNDLE_DIR, "sample_subtitle_video.mp4")
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

    start_time = time.time()
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
        elapsed = time.time() - start_time
        if success:
            tasks_status[task_id]["status"] = "completed"
            tasks_status[task_id]["percent"] = 100.0
            tasks_status[task_id]["download_url"] = f"/api/download/{task_id}"
            tasks_status[task_id]["video_url"] = f"/outputs/{os.path.basename(output_path)}"
            db.update_task_status(task_id, "completed", elapsed)
        else:
            tasks_status[task_id]["status"] = "cancelled"
            db.update_task_status(task_id, "cancelled", elapsed)
    except Exception as e:
        elapsed = time.time() - start_time
        tasks_status[task_id]["status"] = "failed"
        tasks_status[task_id]["error"] = str(e)
        db.update_task_status(task_id, "failed", elapsed)


@app.post("/api/process")
async def start_process(
    request: Request,
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

    # 작업 메타데이터 DB 로깅
    info = get_video_info(video_path)
    file_size_mb = round(os.path.getsize(video_path) / (1024 * 1024), 2) if os.path.exists(video_path) else 0.0
    client_ip = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
    if "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    db.create_task_log(
        task_id=task_id,
        ip=client_ip,
        filename=os.path.basename(found_files[0]),
        file_size_mb=file_size_mb,
        resolution=f"{info.get('width', 0)}x{info.get('height', 0)}",
        duration_sec=info.get("duration", 0.0),
        total_frames=info.get("total_frames", 0),
        mode=mode
    )

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
