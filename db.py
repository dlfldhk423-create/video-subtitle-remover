import sqlite3
import os
import time
from typing import Dict, Any, List, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.db")


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """데이터베이스 테이블 생성"""
    with get_db() as conn:
        cursor = conn.cursor()
        # 1. 사이트 접속 로그
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS visit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT,
                user_agent TEXT,
                device TEXT,
                path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. 영상 작업 로그
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT UNIQUE,
                ip TEXT,
                filename TEXT,
                file_size_mb REAL,
                resolution TEXT,
                duration_sec REAL,
                total_frames INTEGER,
                mode TEXT,
                status TEXT,
                processing_time_sec REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def log_visit(ip: str, user_agent: str, path: str):
    """방문자 접속 기록"""
    device = "모바일" if any(k in user_agent.lower() for k in ["iphone", "android", "mobile"]) else "데스크톱"
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO visit_logs (ip, user_agent, device, path) VALUES (?, ?, ?, ?)",
                (ip, user_agent[:250], device, path)
            )
            conn.commit()
    except Exception as e:
        print(f"방문 기록 에러: {e}")


def create_task_log(task_id: str, ip: str, filename: str, file_size_mb: float,
                    resolution: str, duration_sec: float, total_frames: int, mode: str):
    """작업 생성 기록"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO task_logs 
                (task_id, ip, filename, file_size_mb, resolution, duration_sec, total_frames, mode, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'processing')
            """, (task_id, ip, filename, file_size_mb, resolution, duration_sec, total_frames, mode))
            conn.commit()
    except Exception as e:
        print(f"작업 기록 에러: {e}")


def update_task_status(task_id: str, status: str, processing_time_sec: float = 0.0):
    """작업 완료 상태 갱신"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE task_logs 
                SET status = ?, processing_time_sec = ?
                WHERE task_id = ?
            """, (status, round(processing_time_sec, 2), task_id))
            conn.commit()
    except Exception as e:
        print(f"작업 상태 갱신 에러: {e}")


def get_dashboard_stats() -> Dict[str, Any]:
    """관리자 요약 통계 지표 계산 (실제 페이지 방문만 집계)"""
    with get_db() as conn:
        cursor = conn.cursor()

        # 실제 사이트 메인 페이지 접속 수 (path = '/')
        cursor.execute("SELECT COUNT(*) FROM visit_logs WHERE path = '/'")
        total_visits = cursor.fetchone()[0]

        # 오늘 방문 수
        cursor.execute("SELECT COUNT(*) FROM visit_logs WHERE path = '/' AND date(created_at) = date('now')")
        today_visits = cursor.fetchone()[0]

        # 총 처리 작업 수
        cursor.execute("SELECT COUNT(*) FROM task_logs")
        total_tasks = cursor.fetchone()[0]

        # 성공 완료 작업 수
        cursor.execute("SELECT COUNT(*) FROM task_logs WHERE status = 'completed'")
        completed_tasks = cursor.fetchone()[0]

        # 총 처리된 영상 시간(초)
        cursor.execute("SELECT COALESCE(SUM(duration_sec), 0) FROM task_logs WHERE status = 'completed'")
        total_video_seconds = cursor.fetchone()[0]

        # 모바일 vs 데스크톱 비율
        cursor.execute("SELECT device, COUNT(*) FROM visit_logs WHERE path = '/' GROUP BY device")
        devices = dict(cursor.fetchall())

        return {
            "total_visits": total_visits,
            "today_visits": today_visits,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "total_video_minutes": round(total_video_seconds / 60, 1),
            "desktop_visits": devices.get("데스크톱", 0),
            "mobile_visits": devices.get("모바일", 0),
        }


def get_recent_activity(limit: int = 50) -> List[Dict[str, Any]]:
    """최근 작업 목록"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT task_id, ip, filename, file_size_mb, resolution, duration_sec, 
                   mode, status, processing_time_sec, datetime(created_at, 'localtime') as created_at
            FROM task_logs
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def get_recent_visitors(limit: int = 50) -> List[Dict[str, Any]]:
    """최근 방문자 목록"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ip, device, user_agent, path, datetime(created_at, 'localtime') as created_at
            FROM visit_logs
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


# 모듈 로드 시 DB 초기화
init_db()
