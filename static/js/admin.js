/**
 * Subtitle Remover Studio - Admin Dashboard Client Logic
 */

document.addEventListener('DOMContentLoaded', () => {
  const authModal = document.getElementById('auth-modal');
  const authForm = document.getElementById('auth-form');
  const authInput = document.getElementById('admin-pass-input');
  const authError = document.getElementById('auth-error');
  const dashboardApp = document.getElementById('dashboard-app');
  const btnLogout = document.getElementById('btn-logout');

  const autoRefreshToggle = document.getElementById('auto-refresh-toggle');
  const btnManualRefresh = document.getElementById('btn-manual-refresh');
  const btnCleanStorage = document.getElementById('btn-clean-storage');
  const logSearchInput = document.getElementById('log-search-input');

  const valTotalVisits = document.getElementById('val-total-visits');
  const badgeTodayVisits = document.getElementById('badge-today-visits');
  const valDeviceRatio = document.getElementById('val-device-ratio');
  const valTotalTasks = document.getElementById('val-total-tasks');
  const badgeCompletedTasks = document.getElementById('badge-completed-tasks');
  const valSuccessRate = document.getElementById('val-success-rate');
  const valVideoMinutes = document.getElementById('val-video-minutes');

  const valStorageUploads = document.getElementById('val-storage-uploads');
  const valStorageOutputs = document.getElementById('val-storage-outputs');
  const valStorageTotal = document.getElementById('val-storage-total');

  const countTasks = document.getElementById('count-tasks');
  const countVisitors = document.getElementById('count-visitors');
  const taskTableBody = document.getElementById('task-table-body');
  const visitorTableBody = document.getElementById('visitor-table-body');

  let allTasks = [];
  let allVisitors = [];
  let refreshTimer = null;

  // 1. 인증 확인
  const savedToken = localStorage.getItem('admin_token');
  if (savedToken === 'admin_authenticated') {
    showDashboard();
  }

  authForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const pass = authInput.value;
    const formData = new FormData();
    formData.append('password', pass);

    try {
      const res = await fetch('/api/admin/login', {
        method: 'POST',
        body: formData
      });

      if (!res.ok) throw new Error('비밀번호 오류');
      const data = await res.json();
      localStorage.setItem('admin_token', data.token);
      showDashboard();
    } catch (err) {
      authError.classList.remove('hidden');
    }
  });

  btnLogout.addEventListener('click', () => {
    localStorage.removeItem('admin_token');
    location.reload();
  });

  function showDashboard() {
    authModal.classList.add('hidden');
    dashboardApp.classList.remove('hidden');
    loadDashboardData();
    setupAutoRefresh();
  }

  // 2. 대시보드 데이터 로드
  async function loadDashboardData() {
    try {
      const res = await fetch('/api/admin/stats');
      if (!res.ok) return;

      const data = await res.json();
      renderStats(data.stats, data.storage);

      allTasks = data.recent_tasks || [];
      allVisitors = data.recent_visitors || [];

      countTasks.textContent = allTasks.length;
      countVisitors.textContent = allVisitors.length;

      renderTasks(allTasks);
      renderVisitors(allVisitors);
    } catch (e) {
      console.error('대시보드 데이터 로드 실패:', e);
    }
  }

  function renderStats(stats, storage) {
    if (!stats) return;

    valTotalVisits.textContent = stats.total_visits || 0;
    badgeTodayVisits.textContent = `+${stats.today_visits || 0} 오늘`;

    const totalV = (stats.desktop_visits || 0) + (stats.mobile_visits || 0);
    const deskPct = totalV > 0 ? Math.round((stats.desktop_visits / totalV) * 100) : 0;
    const mobPct = totalV > 0 ? (100 - deskPct) : 0;
    valDeviceRatio.textContent = `데스크톱 ${deskPct}% / 모바일 ${mobPct}%`;

    valTotalTasks.textContent = stats.total_tasks || 0;
    badgeCompletedTasks.textContent = `${stats.completed_tasks || 0}건 완료`;

    const rate = stats.total_tasks > 0 ? Math.round((stats.completed_tasks / stats.total_tasks) * 100) : 100;
    valSuccessRate.textContent = `성공률 ${rate}%`;

    valVideoMinutes.textContent = stats.total_video_minutes || '0.0';

    if (storage) {
      valStorageUploads.textContent = `${storage.uploads_mb} MB`;
      valStorageOutputs.textContent = `${storage.outputs_mb} MB`;
      valStorageTotal.textContent = `${storage.total_mb} MB`;
    }
  }

  function renderTasks(tasks) {
    if (!tasks || tasks.length === 0) {
      taskTableBody.innerHTML = '<tr><td colspan="9" class="td-empty">아직 처리된 영상 작업 기록이 없습니다.</td></tr>';
      return;
    }

    const query = logSearchInput.value.toLowerCase().trim();
    const filtered = tasks.filter(t => 
      !query || 
      (t.ip && t.ip.toLowerCase().includes(query)) ||
      (t.filename && t.filename.toLowerCase().includes(query))
    );

    taskTableBody.innerHTML = filtered.map(t => {
      let statusBadge = '<span class="status-badge status-processing">처리중</span>';
      if (t.status === 'completed') statusBadge = '<span class="status-badge status-completed">완료</span>';
      else if (t.status === 'failed') statusBadge = '<span class="status-badge status-failed">실패</span>';
      else if (t.status === 'cancelled') statusBadge = '<span class="status-badge status-cancelled">취소</span>';

      const modeName = t.mode === 'smart_text' ? '✨ 스마트 텍스트' : (t.mode === 'full_box' ? '🔲 영역 전체' : '💧 블러');

      return `
        <tr>
          <td><span style="font-family:monospace; color:var(--text-muted);">${t.created_at || '-'}</span></td>
          <td><strong style="font-family:monospace; color:var(--accent-secondary);">${t.ip || 'unknown'}</strong></td>
          <td title="${t.filename}">${truncate(t.filename || 'noname', 24)}</td>
          <td>${t.resolution || '-'}</td>
          <td>${t.duration_sec ? t.duration_sec + '초' : '-'}</td>
          <td>${t.file_size_mb ? t.file_size_mb + 'MB' : '-'}</td>
          <td>${modeName}</td>
          <td>${t.processing_time_sec ? t.processing_time_sec + '초' : '-'}</td>
          <td>${statusBadge}</td>
        </tr>
      `;
    }).join('');
  }

  function renderVisitors(visitors) {
    if (!visitors || visitors.length === 0) {
      visitorTableBody.innerHTML = '<tr><td colspan="5" class="td-empty">아직 접속자 기록이 없습니다.</td></tr>';
      return;
    }

    const query = logSearchInput.value.toLowerCase().trim();
    const filtered = visitors.filter(v => 
      !query || 
      (v.ip && v.ip.toLowerCase().includes(query)) ||
      (v.device && v.device.toLowerCase().includes(query)) ||
      (v.user_agent && v.user_agent.toLowerCase().includes(query))
    );

    visitorTableBody.innerHTML = filtered.map(v => `
      <tr>
        <td><span style="font-family:monospace; color:var(--text-muted);">${v.created_at || '-'}</span></td>
        <td><strong style="font-family:monospace; color:var(--accent-secondary);">${v.ip || 'unknown'}</strong></td>
        <td><span class="badge ${v.device === '모바일' ? 'badge-accent' : 'badge-outline'}">${v.device}</span></td>
        <td><code>${v.path}</code></td>
        <td title="${v.user_agent}"><span style="color:var(--text-dim); font-size:0.78rem;">${truncate(v.user_agent, 45)}</span></td>
      </tr>
    `).join('');
  }

  function truncate(str, max) {
    if (!str) return '';
    return str.length > max ? str.substring(0, max) + '...' : str;
  }

  // 3. 탭 전환
  document.querySelectorAll('.dash-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.dash-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');

      const targetId = tab.getAttribute('data-target');
      document.querySelectorAll('.tab-panel').forEach(p => {
        p.classList.add('hidden');
        p.classList.remove('active');
      });
      const panel = document.getElementById(targetId);
      panel.classList.remove('hidden');
      panel.classList.add('active');
    });
  });

  // 검색 필터링
  logSearchInput.addEventListener('input', () => {
    renderTasks(allTasks);
    renderVisitors(allVisitors);
  });

  btnManualRefresh.addEventListener('click', () => {
    btnManualRefresh.style.transform = 'rotate(180deg)';
    setTimeout(() => btnManualRefresh.style.transform = 'none', 300);
    loadDashboardData();
  });

  // 실시간 타이머
  function setupAutoRefresh() {
    if (refreshTimer) clearInterval(refreshTimer);
    if (autoRefreshToggle.checked) {
      refreshTimer = setInterval(loadDashboardData, 10000);
    }
  }

  autoRefreshToggle.addEventListener('change', setupAutoRefresh);

  // 4. 스토리지 청소
  btnCleanStorage.addEventListener('click', async () => {
    if (confirm('임시 업로드 영상과 생성된 결과물 파일들을 모두 정리하시겠습니까? (DB 로그는 보존됩니다)')) {
      const res = await fetch('/api/admin/clean', { method: 'POST' });
      const data = await res.json();
      alert(`정리 완료: ${data.cleaned_files}개 파일 삭제 (${data.cleaned_mb} MB 절약)`);
      loadDashboardData();
    }
  });
});
