import os
import sys
import cv2
import numpy as np
import subprocess
import time
import shutil
from typing import List, Dict, Any, Callable, Optional


def get_ffmpeg_cmd() -> str:
    """Windows/Mac 환경에서 번들된 ffmpeg.exe 또는 시스템 ffmpeg 경로를 안전하게 반환합니다."""
    candidates = []
    if getattr(sys, 'frozen', False):
        candidates.append(os.path.join(getattr(sys, '_MEIPASS', ''), "ffmpeg.exe"))
        candidates.append(os.path.join(os.path.dirname(sys.executable), "ffmpeg.exe"))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ffmpeg.exe"))
    candidates.append("ffmpeg.exe")
    candidates.append("ffmpeg")

    for path in candidates:
        if os.path.isabs(path) and os.path.isfile(path):
            return path
        elif shutil.which(path):
            return path
    return "ffmpeg"


def extract_frame_at_time(video_path: str, time_sec: float = 0.0) -> Optional[np.ndarray]:
    """비디오의 특정 시간(초)에 해당하는 프레임 이미지를 추출합니다."""
    if not os.path.exists(video_path):
        return None
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_no = int(time_sec * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
    ret, frame = cap.read()
    if not ret:
        # 첫 프레임으로 폴백
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ret, frame = cap.read()
    cap.release()
    return frame if ret else None


def get_video_info(video_path: str) -> Dict[str, Any]:
    """비디오의 메타데이터(해상도, FPS, 총 프레임, 재생 시간)를 가져옵니다."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {}

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0

    cap.release()
    return {
        "width": width,
        "height": height,
        "fps": round(fps, 2),
        "total_frames": total_frames,
        "duration": round(duration, 2),
    }


def create_smart_subtitle_mask(roi_img: np.ndarray, dilation: int = 3, sensitivity: int = 50) -> np.ndarray:
    """
    자막 영역(ROI) 내에서 자막 텍스트 픽셀(흰색/노란색/밝은 글자 및 검은 외곽선)을
    정밀하게 감지하여 마스크(바이너리 이미지)를 생성합니다.
    주변 배경은 마스킹하지 않고 글자만 타깃팅하여 자연스럽게 지웁니다.
    """
    gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)

    # 1. 대비 강조 (CLAHE)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # 2. 적응형 임계값 (Adaptive Threshold)을 통한 텍스트 및 엣지 추출
    thresh1 = cv2.adaptiveThreshold(
        enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, -5
    )

    # 3. 색상 기반 (자막은 대부분 흰색, 노란색, 또는 밝은 원색 계열)
    hsv = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)
    # 밝은 색(흰색/연노랑 등 높은 명도)
    white_mask = cv2.inRange(hsv, np.array([0, 0, 160]), np.array([180, 70, 255]))
    # 노란색 자막
    yellow_mask = cv2.inRange(hsv, np.array([15, 80, 150]), np.array([35, 255, 255]))
    # 고명도/자막 텍스트
    color_mask = cv2.bitwise_or(white_mask, yellow_mask)

    # 4. 소벨 엣지 (자막의 테두리 윤곽)
    grad_x = cv2.Sobel(gray, cv2.CV_16S, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_16S, 0, 1, ksize=3)
    abs_grad_x = cv2.convertScaleAbs(grad_x)
    abs_grad_y = cv2.convertScaleAbs(grad_y)
    grad = cv2.addWeighted(abs_grad_x, 0.5, abs_grad_y, 0.5, 0)
    _, edge_mask = cv2.threshold(grad, 40, 255, cv2.THRESH_BINARY)

    # 마스크 결합 (색상 + 적응형 임계값 + 엣지)
    combined = cv2.bitwise_or(color_mask, thresh1)
    combined = cv2.bitwise_or(combined, edge_mask)

    # 노이즈 제거 (작은 점 제거)
    kernel_clean = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    cleaned = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel_clean)

    # 마스크 팽창(Dilation): 글자 주변 픽셀 및 안티앨리어싱 경계까지 충분히 커버
    dilate_size = max(1, dilation)
    kernel_dilate = cv2.getStructuringElement(cv2.MORPH_RECT, (dilate_size * 2 + 1, dilate_size * 2 + 1))
    final_mask = cv2.dilate(cleaned, kernel_dilate, iterations=1)

    return final_mask


def inpaint_single_frame(
    frame: np.ndarray,
    rois: List[Dict[str, int]],
    mode: str = "smart_text",  # "smart_text", "full_box", "blur"
    inpaint_radius: int = 4,
    method: str = "telea",     # "telea", "ns"
    dilation: int = 3
) -> np.ndarray:
    """
    단일 프레임에 대해 지정된 ROIs(자막 사각형 영역 목록)의 자막을 제거합니다.
    """
    h, w = frame.shape[:2]
    result = frame.copy()

    inpaint_method = cv2.INPAINT_TELEA if method == "telea" else cv2.INPAINT_NS
    full_mask = np.zeros((h, w), dtype=np.uint8)

    for roi in rois:
        rx = max(0, int(roi.get("x", 0)))
        ry = max(0, int(roi.get("y", 0)))
        rw = max(1, int(roi.get("width", 0)))
        rh = max(1, int(roi.get("height", 0)))

        # 이미지 범위 벗어남 방지
        rx = min(rx, w - 1)
        ry = min(ry, h - 1)
        rw = min(rw, w - rx)
        rh = min(rh, h - ry)

        if rw <= 0 or rh <= 0:
            continue

        if mode == "blur":
            # 블러/가림 모드: 부드러운 모자이크/블러 블렌딩
            roi_crop = result[ry:ry + rh, rx:rx + rw]
            blurred = cv2.GaussianBlur(roi_crop, (25, 25), 30)
            result[ry:ry + rh, rx:rx + rw] = blurred
        elif mode == "full_box":
            # 영역 전체 인페인팅: 박스 전체를 마스킹하여 주변 배경으로 채움
            full_mask[ry:ry + rh, rx:rx + rw] = 255
        else:
            # 스마트 텍스트 모드: 자막 글자만 마스크 생성
            roi_crop = frame[ry:ry + rh, rx:rx + rw]
            sub_mask = create_smart_subtitle_mask(roi_crop, dilation=dilation)
            full_mask[ry:ry + rh, rx:rx + rw] = cv2.bitwise_or(full_mask[ry:ry + rh, rx:rx + rw], sub_mask)

    if mode in ["smart_text", "full_box"] and np.count_nonzero(full_mask) > 0:
        result = cv2.inpaint(result, full_mask, inpaint_radius, inpaint_method)

    return result, full_mask


def process_video_subtitles(
    input_video_path: str,
    output_video_path: str,
    rois: List[Dict[str, int]],
    mode: str = "smart_text",
    inpaint_radius: int = 4,
    method: str = "telea",
    dilation: int = 3,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_flag: Optional[Callable[[], bool]] = None
) -> bool:
    """
    비디오 전체를 프레임 단위로 읽어 자막을 제거하고,
    ffmpeg를 이용해 원본 오디오를 합성하여 최종 비디오를 생성합니다.
    """
    if not os.path.exists(input_video_path):
        raise FileNotFoundError(f"입력 비디오를 찾을 수 없습니다: {input_video_path}")

    cap = cv2.VideoCapture(input_video_path)
    if not cap.isOpened():
        raise RuntimeError("비디오 파일을 열 수 없습니다.")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # 임시 비디오 경로 (영상 스트림만 처리)
    temp_dir = os.path.dirname(output_video_path)
    temp_video_path = os.path.join(temp_dir, f"temp_no_audio_{int(time.time())}.mp4")

    # 고화질 비디오 라이터
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(temp_video_path, fourcc, fps, (width, height))

    processed_frames = 0
    start_time = time.time()

    try:
        while True:
            if cancel_flag and cancel_flag():
                cap.release()
                out.release()
                if os.path.exists(temp_video_path):
                    os.remove(temp_video_path)
                return False

            ret, frame = cap.read()
            if not ret:
                break

            # 프레임 인페인팅
            cleaned_frame, _ = inpaint_single_frame(
                frame=frame,
                rois=rois,
                mode=mode,
                inpaint_radius=inpaint_radius,
                method=method,
                dilation=dilation
            )

            out.write(cleaned_frame)
            processed_frames += 1

            if progress_callback and (processed_frames % 5 == 0 or processed_frames == total_frames):
                elapsed = time.time() - start_time
                fps_speed = processed_frames / elapsed if elapsed > 0 else 0
                remaining_frames = max(0, total_frames - processed_frames)
                eta_seconds = remaining_frames / fps_speed if fps_speed > 0 else 0
                percent = round((processed_frames / total_frames) * 100, 1) if total_frames > 0 else 0

                progress_callback({
                    "current_frame": processed_frames,
                    "total_frames": total_frames,
                    "percent": min(100.0, percent),
                    "fps_speed": round(fps_speed, 1),
                    "eta_seconds": int(eta_seconds),
                    "status": "processing"
                })

    finally:
        cap.release()
        out.release()

    if cancel_flag and cancel_flag():
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)
        return False

    # 원본 오디오 추출 및 합성을 위한 FFmpeg 실행
    # (오디오가 있는 경우 고음질 결합, 없는 경우 비디오만 인코딩)
    try:
        if progress_callback:
            progress_callback({
                "current_frame": total_frames,
                "total_frames": total_frames,
                "percent": 99.0,
                "status": "muxing_audio"
            })

        ffmpeg_bin = get_ffmpeg_cmd()
        # ffmpeg로 H.264 인코딩 및 원본 오디오 스트림 복사
        # -sn 플래그는 컨테이너에 내장된 소프트 자막 트랙도 함께 제거
        cmd = [
            ffmpeg_bin, "-y",
            "-i", temp_video_path,
            "-i", input_video_path,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "fast",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            "-map", "0:v:0",
            "-map", "1:a:0?",  # 오디오가 있으면 매핑, 없으면 무시
            "-sn",             # 소프트 자막 스트림도 완전 제거
            output_video_path
        ]

        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            # 오디오 매핑 실패 시 비디오만 저장
            cmd_fallback = [
                ffmpeg_bin, "-y",
                "-i", temp_video_path,
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "fast",
                "-crf", "18",
                "-sn",
                output_video_path
            ]
            subprocess.run(cmd_fallback, check=True)

        if progress_callback:
            progress_callback({
                "current_frame": total_frames,
                "total_frames": total_frames,
                "percent": 100.0,
                "status": "completed"
            })

    finally:
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)

    return True
