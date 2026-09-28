/**
 * AI Video Subtitle Remover Studio - Interactive Client Logic
 */

document.addEventListener('DOMContentLoaded', () => {
  // 상태 변수
  let currentVideoId = null;
  let videoInfo = null;
  let currentFrameImage = new Image();
  let currentFrameTime = 0.0;
  let activeROIs = []; // [{x, y, width, height}, ...] 비디오 원본 픽셀 기준
  let currentTaskId = null;
  let progressInterval = null;

  // DOM 요소 캐싱
  const dropZone = document.getElementById('drop-zone');
  const fileInput = document.getElementById('video-file-input');
  const btnSelectFile = document.getElementById('btn-select-file');
  const btnLoadSample = document.getElementById('btn-load-sample');
  const uploadLoading = document.getElementById('upload-loading');
  const uploadStatusText = document.getElementById('upload-status-text');

  // 시니어 가이드 접기/펼치기
  const seniorGuideToggle = document.getElementById('senior-guide-toggle');
  const seniorGuideBody = document.getElementById('senior-guide-body');
  const guideToggleText = document.getElementById('guide-toggle-text');
  const toggleArrow = document.getElementById('toggle-arrow');

  if (seniorGuideToggle) {
    seniorGuideToggle.addEventListener('click', () => {
      const isHidden = seniorGuideBody.classList.toggle('hidden');
      toggleArrow.classList.toggle('collapsed', isHidden);
      guideToggleText.textContent = isHidden ? '설명 보기' : '설명 닫기';
    });
  }

  const uploadSection = document.getElementById('upload-section');
  const editorSection = document.getElementById('editor-section');
  const progressSection = document.getElementById('progress-section');
  const resultSection = document.getElementById('result-section');

  const frameCanvas = document.getElementById('frame-canvas');
  const canvasCtx = frameCanvas.getContext('2d');
  const canvasContainer = document.getElementById('canvas-container');
  const selectionBox = document.getElementById('selection-box');

  const videoMetaBadge = document.getElementById('video-meta-badge');
  const timeSlider = document.getElementById('time-slider');
  const currentTimeText = document.getElementById('current-time-text');
  const roiBadges = document.getElementById('roi-badges');

  const presetBottom = document.getElementById('preset-bottom');
  const presetBottomWide = document.getElementById('preset-bottom-wide');
  const presetTop = document.getElementById('preset-top');
  const presetClear = document.getElementById('preset-clear');

  const maskDilation = document.getElementById('mask-dilation');
  const valDilation = document.getElementById('val-dilation');
  const inpaintRadius = document.getElementById('inpaint-radius');
  const valRadius = document.getElementById('val-radius');

  const btnPreview = document.getElementById('btn-preview');
  const previewCard = document.getElementById('preview-card');
  const previewImgCleaned = document.getElementById('preview-img-cleaned');
  const previewImgMask = document.getElementById('preview-img-mask');
  const previewTabs = document.querySelectorAll('.tab-btn');

  const btnStartProcess = document.getElementById('btn-start-process');
  const btnCancelProcess = document.getElementById('btn-cancel-process');

  const progressBarFill = document.getElementById('progress-bar-fill');
  const metricPercent = document.getElementById('metric-percent');
  const metricFrames = document.getElementById('metric-frames');
  const metricFps = document.getElementById('metric-fps');
  const metricEta = document.getElementById('metric-eta');

  const resultVideoPlayer = document.getElementById('result-video-player');
  const btnDownloadVideo = document.getElementById('btn-download-video');
  const btnNewVideo = document.getElementById('btn-new-video');

  // 1. 업로드 이벤트
  btnSelectFile.addEventListener('click', (e) => {
    e.stopPropagation();
    fileInput.click();
  });

  btnLoadSample.addEventListener('click', async (e) => {
    e.stopPropagation();
    dropZone.classList.add('hidden');
    uploadLoading.classList.remove('hidden');
    uploadStatusText.textContent = '샘플 비디오를 불러오는 중입니다...';

    try {
      const res = await fetch('/api/sample', { method: 'POST' });
      if (!res.ok) throw new Error('샘플 로드 실패');
      const data = await res.json();
      currentVideoId = data.video_id;
      videoInfo = data.info;
      initEditor(data);
    } catch (err) {
      alert(`오류: ${err.message}`);
      dropZone.classList.remove('hidden');
      uploadLoading.classList.add('hidden');
    }
  });

  dropZone.addEventListener('click', () => fileInput.click());

  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
  });

  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));

  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileUpload(e.target.files[0]);
    }
  });

  async function handleFileUpload(file) {
    if (!file.type.startsWith('video/') && !file.name.match(/\.(mp4|mov|mkv|webm|avi)$/i)) {
      alert('동영상 파일(MP4, MOV, MKV, WebM 등)만 업로드 가능합니다.');
      return;
    }

    dropZone.classList.add('hidden');
    uploadLoading.classList.remove('hidden');
    uploadStatusText.textContent = `"${file.name}" 업로드 및 프레임 분석 중...`;

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '업로드 실패');
      }

      const data = await res.json();
      currentVideoId = data.video_id;
      videoInfo = data.info;

      initEditor(data);
    } catch (err) {
      alert(`오류: ${err.message}`);
      dropZone.classList.remove('hidden');
      uploadLoading.classList.add('hidden');
    }
  }

  // 2. 에디터 초기화
  function initEditor(data) {
    uploadSection.classList.add('hidden');
    editorSection.classList.remove('hidden');

    const durationMin = Math.floor(videoInfo.duration / 60);
    const durationSec = Math.floor(videoInfo.duration % 60);
    const durationText = `${String(durationMin).padStart(2, '0')}:${String(durationSec).padStart(2, '0')}`;

    videoMetaBadge.textContent = `${videoInfo.width}x${videoInfo.height} | ${videoInfo.fps} FPS | ${durationText}`;

    timeSlider.min = 0;
    timeSlider.max = videoInfo.duration;
    timeSlider.value = 0;
    currentTimeText.textContent = `00:00.0 / ${durationText}`;

    // 첫 프레임 로드
    loadFrame(0.0, () => {
      // 기본 추천: 하단 자막 프리셋 자동 적용
      applyPreset('bottom');
    });
  }

  function formatTime(seconds) {
    const min = Math.floor(seconds / 60);
    const sec = (seconds % 60).toFixed(1);
    return `${String(min).padStart(2, '0')}:${sec < 10 ? '0' : ''}${sec}`;
  }

  // 3. 비디오 프레임 로드
  function loadFrame(timeSec, callback) {
    currentFrameTime = timeSec;
    const url = `/api/frame?video_id=${currentVideoId}&time_sec=${timeSec}&t=${Date.now()}`;
    currentFrameImage = new Image();
    currentFrameImage.onload = () => {
      renderCanvas();
      if (callback) callback();
    };
    currentFrameImage.src = url;
  }

  function renderCanvas() {
    if (!currentFrameImage || !currentFrameImage.width) return;

    frameCanvas.width = videoInfo.width;
    frameCanvas.height = videoInfo.height;

    // 프레임 그리기
    canvasCtx.clearRect(0, 0, frameCanvas.width, frameCanvas.height);
    canvasCtx.drawImage(currentFrameImage, 0, 0);

    // 지정된 ROIs 빨간색 윤곽선 표시
    activeROIs.forEach((roi, idx) => {
      canvasCtx.strokeStyle = '#ef4444';
      canvasCtx.lineWidth = Math.max(3, Math.round(videoInfo.width / 500));
      canvasCtx.fillStyle = 'rgba(239, 68, 68, 0.25)';
      canvasCtx.fillRect(roi.x, roi.y, roi.width, roi.height);
      canvasCtx.strokeRect(roi.x, roi.y, roi.width, roi.height);

      // 라벨
      canvasCtx.fillStyle = '#ef4444';
      const labelText = ` 자막 영역 #${idx + 1} `;
      const fontSize = Math.max(14, Math.round(videoInfo.width / 80));
      canvasCtx.font = `bold ${fontSize}px sans-serif`;
      canvasCtx.fillText(labelText, roi.x + 4, Math.max(roi.y - 6, fontSize + 4));
    });
  }

  // 타임라인 슬라이더 조작
  let sliderTimeout = null;
  timeSlider.addEventListener('input', (e) => {
    const val = parseFloat(e.target.value);
    const durationMin = Math.floor(videoInfo.duration / 60);
    const durationSec = Math.floor(videoInfo.duration % 60);
    const totalTimeStr = `${String(durationMin).padStart(2, '0')}:${String(durationSec).padStart(2, '0')}`;
    currentTimeText.textContent = `${formatTime(val)} / ${totalTimeStr}`;

    clearTimeout(sliderTimeout);
    sliderTimeout = setTimeout(() => {
      loadFrame(val);
    }, 80);
  });

  // 4. 캔버스 마우스 드래그로 자막 박스(ROI) 그리기
  let isDragging = false;
  let startX = 0;
  let startY = 0;
  let containerRect = null;

  canvasContainer.addEventListener('mousedown', (e) => {
    if (!videoInfo) return;
    isDragging = true;
    containerRect = canvasContainer.getBoundingClientRect();

    startX = e.clientX - containerRect.left;
    startY = e.clientY - containerRect.top;

    selectionBox.style.left = `${startX}px`;
    selectionBox.style.top = `${startY}px`;
    selectionBox.style.width = '0px';
    selectionBox.style.height = '0px';
    selectionBox.classList.remove('hidden');
  });

  window.addEventListener('mousemove', (e) => {
    if (!isDragging || !containerRect) return;

    const currentX = e.clientX - containerRect.left;
    const currentY = e.clientY - containerRect.top;

    const left = Math.min(startX, currentX);
    const top = Math.min(startY, currentY);
    const width = Math.abs(currentX - startX);
    const height = Math.abs(currentY - startY);

    selectionBox.style.left = `${left}px`;
    selectionBox.style.top = `${top}px`;
    selectionBox.style.width = `${width}px`;
    selectionBox.style.height = `${height}px`;
  });

  window.addEventListener('mouseup', (e) => {
    if (!isDragging) return;
    isDragging = false;
    selectionBox.classList.add('hidden');

    if (!containerRect) return;

    const endX = e.clientX - containerRect.left;
    const endY = e.clientY - containerRect.top;

    const boxW = Math.abs(endX - startX);
    const boxH = Math.abs(endY - startY);

    // 최소 10px 이상 드래그했을 때만 영역 등록
    if (boxW > 10 && boxH > 10) {
      const canvasDisplayW = frameCanvas.clientWidth;
      const canvasDisplayH = frameCanvas.clientHeight;
      const scaleX = videoInfo.width / canvasDisplayW;
      const scaleY = videoInfo.height / canvasDisplayH;

      // 캔버스 내 오프셋 보정
      const canvasRect = frameCanvas.getBoundingClientRect();
      const offsetX = canvasRect.left - containerRect.left;
      const offsetY = canvasRect.top - containerRect.top;

      const clickBoxLeft = Math.min(startX, endX) - offsetX;
      const clickBoxTop = Math.min(startY, endY) - offsetY;

      const realX = Math.max(0, Math.round(clickBoxLeft * scaleX));
      const realY = Math.max(0, Math.round(clickBoxTop * scaleY));
      const realW = Math.min(videoInfo.width - realX, Math.round(boxW * scaleX));
      const realH = Math.min(videoInfo.height - realY, Math.round(boxH * scaleY));

      if (realW > 5 && realH > 5) {
        activeROIs.push({ x: realX, y: realY, width: realW, height: realH });
        updateROIBadges();
        renderCanvas();
      }
    }
  });

  // 프리셋 핸들러
  function applyPreset(type) {
    if (!videoInfo) return;
    const W = videoInfo.width;
    const H = videoInfo.height;

    if (type === 'bottom') {
      // 하단 18% (표준 1줄 자막)
      const roiH = Math.round(H * 0.18);
      const roiY = H - roiH - Math.round(H * 0.04);
      const roiW = Math.round(W * 0.88);
      const roiX = Math.round((W - roiW) / 2);
      activeROIs = [{ x: roiX, y: roiY, width: roiW, height: roiH }];
    } else if (type === 'bottom_wide') {
      // 하단 28% (2줄 이상 자막)
      const roiH = Math.round(H * 0.28);
      const roiY = H - roiH - Math.round(H * 0.02);
      const roiW = Math.round(W * 0.94);
      const roiX = Math.round((W - roiW) / 2);
      activeROIs = [{ x: roiX, y: roiY, width: roiW, height: roiH }];
    } else if (type === 'top') {
      // 상단 타이틀/워터마크
      const roiH = Math.round(H * 0.16);
      const roiY = Math.round(H * 0.03);
      const roiW = Math.round(W * 0.85);
      const roiX = Math.round((W - roiW) / 2);
      activeROIs = [{ x: roiX, y: roiY, width: roiW, height: roiH }];
    } else if (type === 'clear') {
      activeROIs = [];
    }

    updateROIBadges();
    renderCanvas();
  }

  presetBottom.addEventListener('click', () => applyPreset('bottom'));
  presetBottomWide.addEventListener('click', () => applyPreset('bottom_wide'));
  presetTop.addEventListener('click', () => applyPreset('top'));
  presetClear.addEventListener('click', () => applyPreset('clear'));

  function updateROIBadges() {
    roiBadges.innerHTML = '';
    if (activeROIs.length === 0) {
      roiBadges.innerHTML = '<span class="empty-hint">마우스로 화면 위를 드래그하거나 위의 프리셋 버튼을 클릭하세요.</span>';
      return;
    }

    activeROIs.forEach((roi, idx) => {
      const badge = document.createElement('div');
      badge.className = 'roi-badge';
      badge.innerHTML = `
        <span>영역 #${idx + 1} (${roi.width}x${roi.height})</span>
        <button type="button" data-index="${idx}" title="삭제">&times;</button>
      `;
      badge.querySelector('button').addEventListener('click', (e) => {
        const removeIdx = parseInt(e.target.getAttribute('data-index'), 10);
        activeROIs.splice(removeIdx, 1);
        updateROIBadges();
        renderCanvas();
      });
      roiBadges.appendChild(badge);
    });
  }

  // 5. 파라미터 변경 슬라이더 연동
  maskDilation.addEventListener('input', (e) => {
    valDilation.textContent = `${e.target.value} px`;
  });
  inpaintRadius.addEventListener('input', (e) => {
    valRadius.textContent = `${e.target.value} px`;
  });

  // 라디오 카드 활성화 표시
  document.querySelectorAll('.radio-card input[type="radio"]').forEach(radio => {
    radio.addEventListener('change', () => {
      document.querySelectorAll('.radio-card').forEach(rc => rc.classList.remove('selected'));
      radio.closest('.radio-card').classList.add('selected');
    });
  });

  // 6. 실시간 프레임 미리보기
  btnPreview.addEventListener('click', async () => {
    if (activeROIs.length === 0) {
      alert('자막 영역을 하나 이상 지정해주세요.');
      return;
    }

    const mode = document.querySelector('input[name="inpaint-mode"]:checked').value;
    const dilation = parseInt(maskDilation.value, 10);
    const radius = parseInt(inpaintRadius.value, 10);

    btnPreview.disabled = true;
    btnPreview.textContent = '미리보기 계산 중...';

    const formData = new FormData();
    formData.append('video_id', currentVideoId);
    formData.append('time_sec', currentFrameTime);
    formData.append('rois_json', JSON.stringify(activeROIs));
    formData.append('mode', mode);
    formData.append('dilation', dilation);
    formData.append('inpaint_radius', radius);
    formData.append('method', 'telea');

    try {
      const res = await fetch('/api/preview', {
        method: 'POST',
        body: formData
      });

      if (!res.ok) throw new Error('미리보기 생성 실패');
      const data = await res.json();

      previewImgCleaned.src = data.cleaned_base64;
      previewImgMask.src = data.mask_base64;
      previewCard.classList.remove('hidden');
    } catch (err) {
      alert(`미리보기 오류: ${err.message}`);
    } finally {
      btnPreview.disabled = false;
      btnPreview.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
          <circle cx="12" cy="12" r="3"/>
        </svg> 현재 프레임 미리보기 (0.1초)
      `;
    }
  });

  // 미리보기 탭 전환
  previewTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      previewTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      const target = tab.getAttribute('data-tab');
      if (target === 'cleaned') {
        previewImgCleaned.classList.remove('hidden');
        previewImgMask.classList.add('hidden');
      } else {
        previewImgCleaned.classList.add('hidden');
        previewImgMask.classList.remove('hidden');
      }
    });
  });

  // 7. 전체 영상 자막 삭제 프로세스 시작
  btnStartProcess.addEventListener('click', async () => {
    if (activeROIs.length === 0) {
      alert('자막을 삭제할 영역을 지정해주세요.');
      return;
    }

    const mode = document.querySelector('input[name="inpaint-mode"]:checked').value;
    const dilation = parseInt(maskDilation.value, 10);
    const radius = parseInt(inpaintRadius.value, 10);

    const formData = new FormData();
    formData.append('video_id', currentVideoId);
    formData.append('rois_json', JSON.stringify(activeROIs));
    formData.append('mode', mode);
    formData.append('dilation', dilation);
    formData.append('inpaint_radius', radius);
    formData.append('method', 'telea');

    btnStartProcess.disabled = true;

    try {
      const res = await fetch('/api/process', {
        method: 'POST',
        body: formData
      });

      if (!res.ok) throw new Error('작업 시작 실패');
      const data = await res.json();
      currentTaskId = data.task_id;

      // 진행률 화면으로 전환
      editorSection.classList.add('hidden');
      progressSection.classList.remove('hidden');

      startProgressPolling();
    } catch (err) {
      alert(`오류: ${err.message}`);
      btnStartProcess.disabled = false;
    }
  });

  // 진행률 폴링
  function startProgressPolling() {
    if (progressInterval) clearInterval(progressInterval);

    progressInterval = setInterval(async () => {
      if (!currentTaskId) return;

      try {
        const res = await fetch(`/api/progress/${currentTaskId}`);
        if (!res.ok) return;

        const data = await res.json();

        // UI 갱신
        const pct = data.percent || 0.0;
        progressBarFill.style.width = `${pct}%`;
        metricPercent.textContent = `${pct.toFixed(1)}%`;

        if (data.current_frame && data.total_frames) {
          metricFrames.textContent = `${data.current_frame} / ${data.total_frames}`;
        }
        if (data.fps_speed) {
          metricFps.textContent = `${data.fps_speed} FPS`;
        }
        if (data.eta_seconds !== undefined) {
          const etaMin = Math.floor(data.eta_seconds / 60);
          const etaSec = Math.floor(data.eta_seconds % 60);
          metricEta.textContent = `${etaMin}분 ${etaSec}초`;
        }

        if (data.status === 'muxing_audio') {
          document.getElementById('progress-status-desc').textContent = '고음질 원본 오디오 스트림을 합성하고 있습니다...';
        }

        if (data.status === 'completed') {
          clearInterval(progressInterval);
          showCompletedResult(data);
        } else if (data.status === 'failed') {
          clearInterval(progressInterval);
          alert(`오류 발생: ${data.error || '알 수 없는 오류'}`);
          location.reload();
        } else if (data.status === 'cancelled') {
          clearInterval(progressInterval);
          alert('작업이 취소되었습니다.');
          location.reload();
        }
      } catch (e) {
        console.error('진행률 조회 실패:', e);
      }
    }, 500);
  }

  // 8. 작업 취소
  btnCancelProcess.addEventListener('click', async () => {
    if (!currentTaskId) return;
    if (confirm('진행 중인 자막 삭제 작업을 취소하시겠습니까?')) {
      await fetch(`/api/cancel/${currentTaskId}`, { method: 'POST' });
    }
  });

  // 9. 완료 결과 화면
  function showCompletedResult(data) {
    progressSection.classList.add('hidden');
    resultSection.classList.remove('hidden');

    resultVideoPlayer.src = data.video_url;
    btnDownloadVideo.href = data.download_url;
  }

  btnNewVideo.addEventListener('click', () => {
    location.reload();
  });
});
