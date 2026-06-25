#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scheduled_run.py - CrossMart Ops 定时任务入口
================================================================================
1. 确保 Edge 在 9225 端口运行（系统默认 profile，带卖家精灵插件）
2. 调用 backend/run_ops.py --all 跑配置里所有关键词的竞品运营监测
3. 自动 git add/commit/push frontend/data（触发 GitHub Pages 部署）

定时任务的 .bat 调用本脚本。
⛔ 铁律：Edge 唯一默认账户（端口 9225），卖家精灵需已登录。
"""
import os
import sys
import io

os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)


def _port_alive(port=9225):
    import urllib.request, json as _json
    try:
        req = urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=3)
        tabs = _json.loads(req.read())
        return bool(tabs is not None)
    except Exception:
        return False


def _kill_all_edge():
    import subprocess, time as _time
    try:
        subprocess.run(["taskkill", "/F", "/IM", "msedge.exe", "/T"],
                       capture_output=True, text=True)
        print("[scheduled_run] 已 taskkill 所有 msedge 进程")
    except Exception as e:
        print(f"[scheduled_run] taskkill 失败: {e}")
    _time.sleep(3)


def ensure_edge():
    try:
        from browser.cdp_bridge import ensure_edge_running, get_tab_count
        if _port_alive(9225):
            cnt = get_tab_count(9225)
            print(f"[scheduled_run] Edge 9225 已就绪（无需重启），标签页={cnt}")
            return True
        print("[scheduled_run] 9225 端口未开，先杀掉所有 Edge 再重启...")
        _kill_all_edge()
        ok = ensure_edge_running(port=9225)
        cnt = get_tab_count(9225) if ok else 0
        print(f"[scheduled_run] Edge 9225 就绪={ok}, 当前标签页={cnt}")
        if not ok or not _port_alive(9225):
            print("[scheduled_run] 首次启动后端口仍不通，再杀一次并重试...")
            _kill_all_edge()
            ok = ensure_edge_running(port=9225)
            cnt = get_tab_count(9225) if ok else 0
            print(f"[scheduled_run] 重试结果 就绪={ok}, 标签页={cnt}")
        return ok and _port_alive(9225)
    except Exception as e:
        print(f"[scheduled_run] 启动 Edge 失败: {e}")
        return False


def git_push():
    """提交并推送 frontend/data 更新（触发 Pages 部署）。"""
    import subprocess
    try:
        from datetime import datetime
        msg = f"data: 定时运营监测更新 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        subprocess.run(["git", "add", "frontend/data"], cwd=PROJECT_ROOT,
                       capture_output=True, text=True, timeout=60)
        r = subprocess.run(["git", "commit", "-m", msg], cwd=PROJECT_ROOT,
                           capture_output=True, text=True, timeout=60)
        if "nothing to commit" in (r.stdout + r.stderr):
            print("[scheduled_run] 无数据变化，跳过 push")
            return
        subprocess.run(["git", "push", "origin", "main"], cwd=PROJECT_ROOT,
                       capture_output=True, text=True, timeout=300)
        print("[scheduled_run] ✅ 已 git push 运营数据")
    except subprocess.TimeoutExpired:
        print("[scheduled_run] ⚠️ git push 超时(300s)，跳过推送避免阻塞")
    except Exception as e:
        print(f"[scheduled_run] git push 失败: {str(e)[:150]}")


def main():
    print("=" * 60)
    print("[scheduled_run] CrossMart Ops 定时任务启动")
    print("=" * 60)

    ensure_edge()

    import subprocess
    run_ops = os.path.join(BACKEND_DIR, "run_ops.py")
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["CDP_PORT"] = "9225"
    rc = subprocess.run(
        [sys.executable, run_ops, "--all"],
        cwd=BACKEND_DIR, env=env, timeout=3600
    ).returncode
    print(f"[scheduled_run] run_ops.py 退出码={rc}")

    git_push()
    sys.exit(rc)


if __name__ == "__main__":
    main()
