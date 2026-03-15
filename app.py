#!/usr/bin/env python3
"""
OnTarget 开源版 - 无需登录的本地文献推送系统
使用固定账户 localuser
"""

import os
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta


# 全局异常处理器，防止意外退出
def handle_exception(exc_type, exc_value, exc_traceback):
    """全局异常处理器"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    print("\n" + "=" * 60, file=sys.stderr)
    print("[全局异常捕获] 未捕获的异常:", file=sys.stderr)
    print(f"类型: {exc_type.__name__}", file=sys.stderr)
    print(f"值: {exc_value}", file=sys.stderr)
    print("\n追踪信息:", file=sys.stderr)
    traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)
    print("=" * 60 + "\n", file=sys.stderr)


sys.excepthook = handle_exception


# 设置线程异常处理器
def handle_thread_exception(args):
    """线程异常处理器"""
    print("\n" + "=" * 60, file=sys.stderr)
    print(f"[线程异常] 线程名称: {args.thread.name}", file=sys.stderr)
    print(f"异常类型: {type(args.exc_value).__name__}", file=sys.stderr)
    print(f"异常值: {args.exc_value}", file=sys.stderr)
    print("\n追踪信息:", file=sys.stderr)
    traceback.print_exception(
        type(args.exc_value),
        args.exc_value,
        args.exc_value.__traceback__,
        file=sys.stderr,
    )
    print("=" * 60 + "\n", file=sys.stderr)


threading.excepthook = handle_thread_exception

base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from functools import wraps

from flask import Flask, render_template, jsonify, request, session, redirect, url_for

env_file = os.path.join(base_dir, ".env")
if os.path.exists(env_file):
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key] = value

from models.user_manager import UserManager, get_predefined_categories, expand_keywords
from core.cache_manager import SmartCache
from services.push_service import PersonalizedPushEngine, PushScheduler
from core.analyzer import OptimizedAnalyzer, AnalysisQueue
from core.system import LiteraturePushSystemV2
from models.keyword_group_manager import KeywordGroupManager
from utils.encryption import get_encryption_manager

LOCAL_USER_ID = "localuser"

app = Flask(__name__, template_folder="templates")
app.secret_key = os.getenv("SECRET_KEY", "ontarget-open-source-secret-key")

base_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(base_dir, "data")
system = LiteraturePushSystemV2(data_dir)

keyword_group_manager = KeywordGroupManager(
    db_path=os.path.join(data_dir, "literature.db")
)

encryption_manager = get_encryption_manager()


def ensure_local_user():
    # 先通过邮箱检查用户是否已存在
    existing_user = system.user_manager.get_user_by_email("local@localhost")
    if existing_user:
        return existing_user["id"]

    # 检查 username
    existing_user = system.user_manager.get_user_by_username(LOCAL_USER_ID)
    if existing_user:
        return existing_user["id"]

    # 创建新用户（可能多个 worker 同时创建，捕获异常）
    try:
        result = system.user_manager.register_user(
            LOCAL_USER_ID, "local@localhost", "localpass", []
        )
        if result.get("success"):
            print(f"✅ 已自动创建本地用户: {LOCAL_USER_ID}")
            new_user = system.user_manager.get_user_by_username(LOCAL_USER_ID)
            if new_user:
                return new_user["id"]
            return result.get("user_id", LOCAL_USER_ID)
    except Exception as e:
        pass

    # 如果创建失败（可能已被其他 worker 创建），再次尝试获取
    existing_user = system.user_manager.get_user_by_email("local@localhost")
    if existing_user:
        return existing_user["id"]

    existing_user = system.user_manager.get_user_by_username(LOCAL_USER_ID)
    if existing_user:
        return existing_user["id"]

    return LOCAL_USER_ID


# ============ API限流配置 (V2.6) ============
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per hour", "50 per minute"],
    storage_uri="memory://",
)

from services.auto_update_service import AutoUpdateService

auto_update_service = AutoUpdateService(system, keyword_group_manager)


@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify(
        {
            "success": False,
            "error": "请求过于频繁，请稍后再试",
            "retry_after": e.description,
        }
    ), 429


@app.after_request
def add_security_headers(response):
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


# ============ 异步更新任务管理 ============
# 存储更新任务状态: {user_id: {'status': 'running'|'completed'|'failed', 'result': {...}, 'started_at': ..., 'completed_at': ...}}
update_tasks = {}
update_tasks_lock = threading.Lock()


def run_update_task(user_id):
    """在后台线程运行更新任务"""
    import sys
    import os

    # 确保异常不会导致进程退出
    def safe_exec(func, *args, **kwargs):
        """安全执行函数，捕获所有异常"""
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"[safe_exec] 函数 {func.__name__} 执行失败: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            raise

    try:
        # 记录线程信息
        current_thread = threading.current_thread()
        print(
            f"[后台任务] 线程信息: 名称={current_thread.name}, ID={current_thread.ident}, 守护={current_thread.daemon}"
        )

        with update_tasks_lock:
            update_tasks[user_id] = {
                "status": "running",
                "result": None,
                "started_at": datetime.now(),
                "completed_at": None,
                "message": "正在获取文献...",
            }

        print(f"[后台任务] 开始为用户 {user_id} 更新文献")
        print(f"[后台任务] 当前工作目录: {os.getcwd()}")

        # 执行更新（在 try 块中，确保异常被捕获）
        try:
            result = system.run_for_user(user_id)
        except Exception as e:
            print(f"[后台任务] system.run_for_user 执行异常:", file=sys.stderr)
            print(f"  异常类型: {type(e).__name__}", file=sys.stderr)
            print(f"  异常信息: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            raise

        # 保存最后更新时间到用户偏好
        try:
            system.user_manager.update_preferences(
                user_id,
                {
                    "last_manual_update_at": datetime.now().isoformat(),
                    "last_manual_update_result": {
                        "fetched": result.get("fetched", 0),
                        "from_cache": result.get("from_cache", 0),
                        "new_analysis": result.get("new_analysis", 0),
                    },
                },
            )
        except Exception as e:
            print(f"[后台任务] 保存更新时间失败: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

        with update_tasks_lock:
            update_tasks[user_id] = {
                "status": "completed",
                "result": result,
                "started_at": update_tasks[user_id]["started_at"],
                "completed_at": datetime.now(),
                "message": f"获取完成: {result.get('fetched', 0)} 篇新文献",
            }

        print(f"[后台任务] ✓ 用户 {user_id} 更新完成")
        print(
            f"[后台任务] 结果: 获取={result.get('fetched', 0)}, 缓存={result.get('from_cache', 0)}, 新分析={result.get('new_analysis', 0)}"
        )

    except MemoryError:
        print(f"[后台任务] ❌ 内存不足", file=sys.stderr)
        with update_tasks_lock:
            update_tasks[user_id] = {
                "status": "failed",
                "result": {"error": "内存不足"},
                "started_at": update_tasks[user_id].get("started_at", datetime.now()),
                "completed_at": datetime.now(),
                "message": "更新失败: 内存不足",
            }
    except SystemExit as e:
        print(
            f"[后台任务] ⚠️ 系统退出: {e.code if hasattr(e, 'code') else 'unknown'}",
            file=sys.stderr,
        )
        # 重新抛出 SystemExit
        raise
    except Exception as e:
        print(f"[后台任务] ❌ 用户 {user_id} 更新失败", file=sys.stderr)
        print(f"  异常类型: {type(e).__name__}", file=sys.stderr)
        print(f"  异常信息: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

        with update_tasks_lock:
            update_tasks[user_id] = {
                "status": "failed",
                "result": {"error": str(e), "type": type(e).__name__},
                "started_at": update_tasks[user_id].get("started_at", datetime.now()),
                "completed_at": datetime.now(),
                "message": f"更新失败: {str(e)}",
            }
    finally:
        print(f"[后台任务] 函数即将返回，用户ID: {user_id}")


def cleanup_old_tasks():
    with update_tasks_lock:
        now = datetime.now()
        expired_users = []
        for user_id, task in update_tasks.items():
            if (
                task.get("completed_at")
                and (now - task["completed_at"]).total_seconds() > 3600
            ):
                expired_users.append(user_id)
        for user_id in expired_users:
            del update_tasks[user_id]
            print(f"[清理] 已删除用户 {user_id} 的旧任务记录")


def start_cleanup_timer():
    def cleanup_loop():
        while True:
            time.sleep(1800)
            cleanup_old_tasks()

    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()
    print("[系统] 后台清理任务已启动")


start_cleanup_timer()

# 移除全局数据库连接，避免多线程锁定问题
# 数据库会在需要时自动初始化
print("✅ 数据库将按需初始化")

ensure_local_user()

if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    try:
        auto_update_service.start()
        print("✅ 自动更新服务已启动")
    except Exception as e:
        print(f"⚠️ 自动更新服务启动失败: {e}")

_LOCAL_USER_ID_CACHE = None


def get_current_user_id():
    global _LOCAL_USER_ID_CACHE
    if _LOCAL_USER_ID_CACHE:
        return _LOCAL_USER_ID_CACHE
    user_id = ensure_local_user()
    _LOCAL_USER_ID_CACHE = user_id
    return user_id


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = get_current_user_id()
        session["user_id"] = user_id
        session["username"] = LOCAL_USER_ID
        return f(*args, **kwargs)

    return decorated_function


@app.route("/")
def index():
    user_id = get_current_user_id()
    groups = keyword_group_manager.get_user_groups(user_id)
    if not groups:
        return redirect("/keywords")
    return render_template("v2_dashboard.html", user_id=user_id)


@app.route("/keywords")
@login_required
def keywords_page():
    return render_template("v2_keywords.html")


@app.route("/api/user/public/<username>")
def api_get_user_public(username):
    return jsonify({"success": False, "error": "开源版不支持公开用户页面"}), 404


@app.route("/api/user/me")
@login_required
def api_get_user():
    user_id = get_current_user_id()
    user = system.user_manager.get_user(user_id)
    if user:
        return jsonify(
            {
                "success": True,
                "user": {
                    "id": user_id,
                    "username": user.get("username", ""),
                    "email": user.get("email", ""),
                    "keywords": user.get("keywords", []),
                    "preferences": user.get("preferences", {}),
                    "avatar": user.get("avatar", ""),
                    "stats": system.push_engine.get_user_stats(user_id),
                },
            }
        )
    return jsonify({"success": False, "error": "用户不存在"}), 404


# API: 更新用户关键词
@app.route("/api/user/keywords", methods=["POST"])
@login_required
def api_update_keywords():
    """更新用户关键词"""
    data = request.json
    user_id = get_current_user_id()

    selected_categories = data.get("categories", [])
    custom_keywords = data.get("custom_keywords", "")

    # 展开关键词
    keywords = expand_keywords(selected_categories)
    if custom_keywords:
        custom_list = [k.strip() for k in custom_keywords.split(",") if k.strip()]
        keywords.extend(custom_list)

    keywords = list(set(keywords))

    result = system.user_manager.update_keywords(user_id, keywords)

    if result["success"]:
        return jsonify(
            {"success": True, "keywords": keywords, "message": "关键词已更新"}
        )
    else:
        return jsonify({"success": False, "error": result["error"]}), 400


# ==================== 关键词组管理 API ====================


# API: 获取用户的关键词组列表
@app.route("/api/user/keyword-groups")
@login_required
def api_get_keyword_groups():
    """获取用户的所有关键词组"""
    user_id = get_current_user_id()

    # 检查是否包含已禁用的组
    include_inactive = request.args.get("include_inactive", "false").lower() == "true"

    # 获取用户的所有组
    groups = keyword_group_manager.get_user_groups(
        user_id, include_inactive=include_inactive
    )

    return jsonify({"success": True, "groups": groups})


# API: 获取用户关键词组汇总（用于Dashboard）
@app.route("/api/user/keyword-groups/summary")
@login_required
def api_get_keyword_groups_summary():
    """获取用户关键词组的汇总信息"""
    user_id = get_current_user_id()

    summary = keyword_group_manager.get_user_groups_summary(user_id)

    return jsonify({"success": True, "summary": summary})


# API: 创建关键词组
@app.route("/api/user/keyword-groups", methods=["POST"])
@login_required
def api_create_keyword_group():
    """创建新的关键词组"""
    user_id = get_current_user_id()
    data = request.json

    # 验证必填字段
    name = data.get("name", "").strip()
    keywords = data.get("keywords", [])

    if not name:
        return jsonify({"success": False, "error": "组名称不能为空"}), 400

    if not keywords or len(keywords) == 0:
        return jsonify({"success": False, "error": "关键词不能为空"}), 400

    # 创建组
    result = keyword_group_manager.create_group(
        user_id=user_id,
        name=name,
        keywords=keywords,
        icon=data.get("icon", "🔬"),
        color=data.get("color", "#5a9a8f"),
        description=data.get("description", ""),
        match_mode=data.get("match_mode", "any"),
        min_match_score=data.get("min_match_score", 0.3),
    )

    if result["success"]:
        return jsonify(
            {
                "success": True,
                "group_id": result["group_id"],
                "group": result["group"],
                "message": "关键词组创建成功",
            }
        )
    else:
        return jsonify({"success": False, "error": result["error"]}), 400


# API: 更新关键词组
@app.route("/api/user/keyword-groups/<group_id>", methods=["PUT"])
@login_required
def api_update_keyword_group(group_id):
    """更新关键词组"""
    user_id = get_current_user_id()
    data = request.json

    # 检查组是否存在
    group = keyword_group_manager.get_group(user_id, group_id)
    if not group:
        return jsonify({"success": False, "error": "关键词组不存在"}), 404

    # 更新组
    result = keyword_group_manager.update_group(user_id, group_id, data)

    if result["success"]:
        return jsonify(
            {"success": True, "group": result["group"], "message": "关键词组更新成功"}
        )
    else:
        return jsonify({"success": False, "error": result["error"]}), 400


# API: 删除关键词组
@app.route("/api/user/keyword-groups/<group_id>", methods=["DELETE"])
@login_required
def api_delete_keyword_group(group_id):
    """删除关键词组"""
    user_id = get_current_user_id()

    result = keyword_group_manager.delete_group(user_id, group_id)

    if result["success"]:
        return jsonify({"success": True, "message": "关键词组已删除"})
    else:
        return jsonify({"success": False, "error": result["error"]}), 400


# API: 重新排序关键词组
@app.route("/api/user/keyword-groups/reorder", methods=["PUT"])
@login_required
def api_reorder_keyword_groups():
    """重新排序关键词组"""
    user_id = get_current_user_id()
    data = request.json
    group_order = data.get("group_order", [])

    if not group_order:
        return jsonify({"success": False, "error": "排序列表不能为空"}), 400

    result = keyword_group_manager.reorder_groups(user_id, group_order)

    if result["success"]:
        return jsonify({"success": True, "message": "排序已更新"})
    else:
        return jsonify({"success": False, "error": result["error"]}), 400

# API: 获取个性化文献（兼容前端调用）
@app.route("/api/papers/personalized")
@login_required
def api_get_personalized_papers():
    user_id = get_current_user_id()

    user = system.user_manager.get_user(user_id)
    if not user:
        return jsonify({"success": False, "error": "用户不存在"}), 404

    user_keywords = user.get("keywords", [])
    
    # 如果用户没有关键词，尝试从第一个激活的关键词组获取
    if not user_keywords:
        try:
            groups = keyword_group_manager.get_user_groups(user_id)
            if groups:
                active_group = next((g for g in groups if g.get('is_active', True)), None)
                if active_group:
                    user_keywords = active_group.get('keywords', [])
        except Exception as e:

    if not user_keywords:
        return jsonify(
            {
                "success": True,
                "papers": [],
                "saved_papers": [],
                "total": 0,
                "message": "请先设置关键词",
            }
        )

    # V2.6 优化：获取分页参数
    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 20))
    except (ValueError, TypeError):
        page = 1
        per_page = 20

    # 限制每页最大数量，防止内存溢出
    per_page = min(per_page, 50)
    page = max(page, 1)

    # 检查是否指定了关键词组
    group_id = request.args.get("group_id")

    if group_id:
        # 使用特定关键词组
        group = keyword_group_manager.get_group(user_id, group_id)
        if not group:
            return jsonify({"success": False, "error": "关键词组不存在"}), 404

        if not group.get("is_active", True):
            return jsonify(
                {
                    "success": True,
                    "papers": [],
                    "saved_papers": [],
                    "total": 0,
                    "message": "该关键词组已禁用",
                }
            )

        # 获取该组的关键词
        user_keywords = group.get("keywords", [])

        # 获取该组收藏的文献（只查询一次）
        saved_papers = keyword_group_manager.get_saved_papers_in_group(
            user_id, group_id
        )
        saved_set = set(saved_papers)

        # 获取用户的所有收藏（用于"仅收藏"筛选）- 批量获取，减少请求次数
        global_saved_papers = keyword_group_manager.get_all_saved_papers_for_user(
            user_id
        )
        global_saved_set = set(global_saved_papers)

        # 从缓存获取所有文献并筛选
        all_papers = list(system.cache.papers_cache.values())

        scored_papers = system.push_engine.get_personalized_papers_for_group(
            user_id=user_id,
            group=group,
            available_papers=all_papers,
            limit=100,  # 内部限制最多返回100篇，避免内存溢出
        )

        # 为文献添加收藏状态
        for paper in scored_papers:
            paper_hash = paper.get("hash")
            paper["is_saved"] = paper_hash in global_saved_set

        # 分页
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_papers = scored_papers[start_idx:end_idx]

        total = len(scored_papers)

        return jsonify(
            {
                "success": True,
                "papers": paginated_papers,
                "saved_papers": saved_papers,
                "global_saved_papers": global_saved_papers,
                "total": total,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_pages": (total + per_page - 1) // per_page,
                    "has_next": end_idx < total,
                    "has_prev": page > 1,
                },
                "group": {
                    "id": group["id"],
                    "name": group["name"],
                    "icon": group.get("icon", "🔬"),
                    "color": group.get("color", "#5a9a8f"),
                    "keywords": group.get("keywords", []),
                },
            }
        )

    # 如果没有指定组，使用所有激活组的关键词（或向后兼容）
    # 从缓存获取文献
    paper_hashes = system.cache.find_papers_by_keywords(user_keywords)
    papers = system.cache.batch_get_papers(paper_hashes)

    # 获取用户收藏的文献（全局）
    saved_papers = keyword_group_manager.get_all_saved_papers_for_user(user_id)

    # 为每篇文献计算个性化分数
    scored_papers = []
    for paper in papers:
        paper_copy = paper.copy()
        score = system.push_engine._calculate_paper_score(paper, user_keywords)
        paper_copy["personalized_score"] = score
        paper_copy["hash"] = paper.get("hash", system.cache._get_paper_hash(paper))
        paper_copy["is_saved"] = paper_copy["hash"] in saved_papers
        scored_papers.append(paper_copy)

    # 按分数排序
    scored_papers.sort(key=lambda x: x.get("personalized_score", 0), reverse=True)

    # 获取分页参数
    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 50))
    except:
        page = 1
        per_page = 50

    # 分页
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paged_papers = scored_papers[start_idx:end_idx]

    # V2.6 优化：服务端分页，只标记当前页的文献为已浏览
    if page == 1:
        paper_hashes = [p["hash"] for p in paged_papers]
        system.push_engine.mark_papers_as_seen(user_id, paper_hashes)

    # V2.6 优化：返回分页后的文献，包含完整分页信息
    total = len(scored_papers)
    return jsonify(
        {
            "success": True,
            "papers": paged_papers,  # V2.6 修复：返回分页后的文献
            "saved_papers": saved_papers,
            "total": total,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total_pages": (total + per_page - 1) // per_page,
                "has_next": end_idx < total,
                "has_prev": page > 1,
            },
        }
    )



# API: 获取特定关键词组的文献
@app.route("/api/user/keyword-groups/<group_id>/papers")
@login_required
def api_get_group_papers(group_id):
    """获取特定关键词组的个性化文献"""
    user_id = get_current_user_id()

    # 获取组信息
    group = keyword_group_manager.get_group(user_id, group_id)
    if not group:
        return jsonify({"success": False, "error": "关键词组不存在"}), 404

    # 检查组是否激活
    if not group.get("is_active", True):
        return jsonify({"success": True, "papers": [], "message": "该关键词组已禁用"})

    # 从缓存获取所有文献
    all_papers = list(system.cache.papers_cache.values())

    # 获取该组的个性化文献
    papers = system.push_engine.get_personalized_papers_for_group(
        user_id=user_id, group=group, available_papers=all_papers, limit=50
    )

    # 获取该组收藏的文献
    saved_hashes = keyword_group_manager.get_saved_papers_in_group(user_id, group_id)
    saved_papers = []
    for h in saved_hashes:
        if h in system.cache.papers_cache:
            saved_papers.append(system.cache.papers_cache[h])

    # 更新访问时间
    keyword_group_manager.update_group_access_time(user_id, group_id)

    # 标记文献为已浏览（关键词组）
    paper_hashes = [p["hash"] for p in papers]
    for ph in paper_hashes:
        keyword_group_manager.mark_paper_viewed_in_group(user_id, group_id, ph)

    return jsonify(
        {
            "success": True,
            "papers": papers,
            "saved_papers": saved_hashes,
            "group": {
                "id": group["id"],
                "name": group["name"],
                "icon": group.get("icon", "🔬"),
                "color": group.get("color", "#5a9a8f"),
            },
        }
    )


# API: 在特定组中收藏文献
@app.route(
    "/api/user/keyword-groups/<group_id>/papers/<paper_hash>/save", methods=["POST"]
)
@login_required
def api_save_paper_to_group(group_id, paper_hash):
    """在特定关键词组中收藏文献"""
    user_id = get_current_user_id()

    # 检查组是否存在
    group = keyword_group_manager.get_group(user_id, group_id)
    if not group:
        return jsonify({"success": False, "error": "关键词组不存在"}), 404

    # 收藏文献
    result = keyword_group_manager.save_paper_to_group(user_id, group_id, paper_hash)

    if result["success"]:
        return jsonify({"success": True, "message": "文献已收藏到该组"})
    else:
        return jsonify({"success": False, "error": result["error"]}), 400


# API: 在特定组中取消收藏文献
@app.route(
    "/api/user/keyword-groups/<group_id>/papers/<paper_hash>/save", methods=["DELETE"]
)
@login_required
def api_unsave_paper_from_group(group_id, paper_hash):
    """在特定关键词组中取消收藏文献"""
    user_id = get_current_user_id()

    # 检查组是否存在
    group = keyword_group_manager.get_group(user_id, group_id)
    if not group:
        return jsonify({"success": False, "error": "关键词组不存在"}), 404

    # 取消收藏
    result = keyword_group_manager.unsave_paper_from_group(
        user_id, group_id, paper_hash
    )

    if result["success"]:
        return jsonify({"success": True, "message": "文献已取消收藏"})
    else:
        return jsonify({"success": False, "error": result["error"]}), 400


# API: 获取预设关键词分类
@app.route("/api/keywords/categories")
def api_get_categories():
    """获取预设关键词分类"""
    categories_dict = get_predefined_categories()
    # 将字典转换为数组格式，方便前端使用
    categories_list = []
    for name, data in categories_dict.items():
        categories_list.append(
            {
                "name": name,
                "icon": data.get("icon", "📚"),
                "keywords": data.get("keywords", []),
            }
        )
    return jsonify({"success": True, "categories": categories_list})


# ==================== 用户设置 API ====================


# API: 获取用户设置
@app.route("/api/user/settings")
@login_required
def api_get_user_settings():
    """获取用户设置"""
    user_id = get_current_user_id()

    settings = system.user_manager.get_user_settings(user_id)

    if settings is None:
        return jsonify({"success": False, "error": "用户不存在"}), 404

    return jsonify({"success": True, "settings": settings})


# API: 更新用户设置
@app.route("/api/user/settings", methods=["PUT"])
@login_required
def api_update_user_settings():
    """更新用户设置"""
    user_id = get_current_user_id()
    data = request.get_json()

    if not data:
        return jsonify({"success": False, "error": "无效的请求数据"})

    # 处理API设置
    if (
        "api_provider" in data
        or "api_key" in data
        or "api_base_url" in data
        or "model" in data
    ):
        api_settings = {
            "api_provider": data.get("api_provider"),
            "api_key": data.get("api_key"),
            "api_base_url": data.get("api_base_url"),
            "model": data.get("model"),
        }
        result = system.user_manager.save_user_api_settings(user_id, api_settings)
        if not result["success"]:
            return jsonify(result), 400

    # 处理更新频率设置
    if "update_frequency_days" in data or "max_auto_analyze" in data:
        update_settings = {
            "update_frequency_days": data.get("update_frequency_days"),
            "max_auto_analyze": data.get("max_auto_analyze"),
        }
        result = system.user_manager.save_user_update_settings(user_id, update_settings)
        if not result["success"]:
            return jsonify(result), 400

    # 处理文献源设置
    if "sources" in data:
        sources = data.get("sources", [])
        if isinstance(sources, list):
            result = system.user_manager.save_user_sources(user_id, sources)
            if not result["success"]:
                return jsonify(result), 400

    return jsonify({"success": True, "message": "设置已保存"})


# API: 获取系统默认API配置（不包含密钥）
@app.route("/api/user/system-api-info")
def api_get_system_api_info():
    """获取系统默认API配置信息"""
    return jsonify(
        {
            "success": True,
            "has_system_api": bool(os.getenv("DEEPSEEK_API_KEY")),
            "default_provider": "deepseek",
            "default_model": "deepseek-chat",
        }
    )


# API: 修改密码
@app.route("/api/user/change-password", methods=["POST"])
@login_required
def api_change_password():
    """修改用户密码"""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "无效的请求数据"}), 400

    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")

    if not current_password or not new_password:
        return jsonify({"success": False, "error": "请提供当前密码和新密码"}), 400

    if len(new_password) < 6:
        return jsonify({"success": False, "error": "新密码至少6位"}), 400

    user_id = get_current_user_id()

    # 验证当前密码
    user = system.user_manager.get_user(user_id)
    if not user:
        return jsonify({"success": False, "error": "用户不存在"}), 404

    user_keywords = user.get("keywords", [])

    # 如果用户没有关键词，尝试从第一个激活的关键词组获取
    if not user_keywords:
        try:
            groups = keyword_group_manager.get_user_groups(user_id)
            if groups:
                active_group = next(
                    (g for g in groups if g.get("is_active", True)), None
                )
                if active_group:
                    user_keywords = active_group.get("keywords", [])
                    print(
                    )
        except Exception as e:

    if not user_keywords:
        return jsonify(
            {
                "success": True,
                "papers": [],
                "saved_papers": [],
                "total": 0,
                "message": "请先设置关键词",
            }
        )

    # V2.6 优化：获取分页参数
    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 20))
    except (ValueError, TypeError):
        page = 1
        per_page = 20

    # 限制每页最大数量，防止内存溢出
    per_page = min(per_page, 50)
    page = max(page, 1)

    # 检查是否指定了关键词组
    group_id = request.args.get("group_id")

    if group_id:
        # 使用特定关键词组
        group = keyword_group_manager.get_group(user_id, group_id)
        if not group:
            return jsonify({"success": False, "error": "关键词组不存在"}), 404

        if not group.get("is_active", True):
            return jsonify(
                {
                    "success": True,
                    "papers": [],
                    "saved_papers": [],
                    "total": 0,
                    "message": "该关键词组已禁用",
                }
            )

        # 获取该组的关键词
        user_keywords = group.get("keywords", [])

        # 获取该组收藏的文献（只查询一次）
        saved_papers = keyword_group_manager.get_saved_papers_in_group(
            user_id, group_id
        )
        saved_set = set(saved_papers)

        # 获取用户的所有收藏（用于"仅收藏"筛选）- 批量获取，减少请求次数
        global_saved_papers = keyword_group_manager.get_all_saved_papers_for_user(
            user_id
        )
        global_saved_set = set(global_saved_papers)

        # 从缓存获取所有文献并筛选
        all_papers = list(system.cache.papers_cache.values())

        scored_papers = system.push_engine.get_personalized_papers_for_group(
            user_id=user_id,
            group=group,
            available_papers=all_papers,
            limit=100,  # 内部限制最多返回100篇，避免内存溢出
        )

        # 标记是否已在当前组收藏
        for paper in scored_papers:
            paper["is_saved"] = paper["hash"] in saved_set

        # V2.6 优化：服务端分页
        total = len(scored_papers)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_papers = scored_papers[start_idx:end_idx]

        # 只有第一页才标记为已浏览（避免重复标记）
        if page == 1:
            # 标记文献为已浏览（全局）
            paper_hashes = [p["hash"] for p in paginated_papers]
            system.push_engine.mark_papers_as_seen(user_id, paper_hashes)

            # 标记文献为已浏览（关键词组）
            for ph in paper_hashes:
                keyword_group_manager.mark_paper_viewed_in_group(user_id, group_id, ph)

        # 更新访问时间
        keyword_group_manager.update_group_access_time(user_id, group_id)

        # 返回结果（包含分页信息）
        return jsonify(
            {
                "success": True,
                "papers": paginated_papers,
                "saved_papers": saved_papers,
                "global_saved_papers": global_saved_papers,
                "total": total,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_pages": (total + per_page - 1) // per_page,
                    "has_next": end_idx < total,
                    "has_prev": page > 1,
                },
                "group": {
                    "id": group["id"],
                    "name": group["name"],
                    "icon": group.get("icon", "🔬"),
                    "color": group.get("color", "#5a9a8f"),
                    "keywords": group.get("keywords", []),
                },
            }
        )

    # 如果没有指定组，使用所有激活组的关键词（或向后兼容）
    # 从缓存获取文献
    paper_hashes = system.cache.find_papers_by_keywords(user_keywords)
    papers = system.cache.batch_get_papers(paper_hashes)

    # 获取用户收藏的文献（全局）
    saved_papers = keyword_group_manager.get_all_saved_papers_for_user(user_id)

    # 为每篇文献计算个性化分数
    scored_papers = []
    for paper in papers:
        paper_copy = paper.copy()
        score = system.push_engine._calculate_paper_score(paper, user_keywords)
        paper_copy["personalized_score"] = score
        paper_copy["hash"] = paper.get("hash", system.cache._get_paper_hash(paper))
        paper_copy["is_saved"] = paper_copy["hash"] in saved_papers
        scored_papers.append(paper_copy)

    # 按分数排序
    scored_papers.sort(key=lambda x: x.get("personalized_score", 0), reverse=True)

    # 获取分页参数
    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 50))
    except:
        page = 1
        per_page = 50

    # 分页
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paged_papers = scored_papers[start_idx:end_idx]

    # V2.6 优化：服务端分页，只标记当前页的文献为已浏览
    if page == 1:
        paper_hashes = [p["hash"] for p in paged_papers]
        system.push_engine.mark_papers_as_seen(user_id, paper_hashes)

    # V2.6 优化：返回分页后的文献，包含完整分页信息
    total = len(scored_papers)
    return jsonify(
        {
            "success": True,
            "papers": paged_papers,  # V2.6 修复：返回分页后的文献
            "saved_papers": saved_papers,
            "total": total,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total_pages": (total + per_page - 1) // per_page,
                "has_next": end_idx < total,
                "has_prev": page > 1,
            },
        }
    )


# API: 保存/取消保存文献
@app.route("/api/papers/save", methods=["POST"])
@login_required
def api_save_paper():
    """保存文献到关键词组"""
    data = request.json
    user_id = get_current_user_id()
    paper_hash = data.get("paper_hash")
    group_id = data.get("group_id")

    if not paper_hash:
        return jsonify({"success": False, "error": "缺少文献标识"}), 400

    if not group_id:
        return jsonify({"success": False, "error": "缺少关键词组ID"}), 400

    # 保存到指定组
    result = keyword_group_manager.save_paper_to_group(user_id, group_id, paper_hash)

    if result["success"]:
        return jsonify({"success": True, "message": "文献已收藏到该组"})
    else:
        return jsonify(result), 400


@app.route("/api/papers/unsave", methods=["POST"])
@login_required
def api_unsave_paper():
    """从关键词组取消保存文献"""
    data = request.json
    user_id = get_current_user_id()
    paper_hash = data.get("paper_hash")
    group_id = data.get("group_id")

    if not paper_hash:
        return jsonify({"success": False, "error": "缺少文献标识"}), 400

    if not group_id:
        return jsonify({"success": False, "error": "缺少关键词组ID"}), 400

    # 从指定组移除收藏
    result = keyword_group_manager.unsave_paper_from_group(
        user_id, group_id, paper_hash
    )

    if result["success"]:
        return jsonify({"success": True, "message": "文献已从该组取消收藏"})
    else:
        return jsonify(result), 400


# API: 获取文献在哪些组被收藏
@app.route("/api/papers/<paper_hash>/saved-groups", methods=["GET"])
@login_required
def api_get_paper_saved_groups(paper_hash):
    """获取文献收藏的所有组"""
    user_id = get_current_user_id()

    # 获取用户的所有组
    groups = keyword_group_manager.get_user_groups(user_id, include_inactive=False)

    # 检查每个组是否收藏了该文献
    saved_groups = []
    for group in groups:
        is_saved = keyword_group_manager.is_paper_saved_in_group(
            user_id, group["id"], paper_hash
        )
        if is_saved:
            saved_groups.append(
                {
                    "id": group["id"],
                    "name": group["name"],
                    "icon": group.get("icon", "🔬"),
                    "color": group.get("color", "#5a9a8f"),
                }
            )

    return jsonify(
        {
            "success": True,
            "paper_hash": paper_hash,
            "saved_groups": saved_groups,
            "count": len(saved_groups),
        }
    )


# API: 触发更新
@app.route("/api/trigger-update", methods=["POST"])
@login_required
@limiter.limit("3 per minute")
def api_trigger_update():
    """手动触发文献更新 - 异步版本"""
    user_id = get_current_user_id()

    # 清理旧任务记录
    cleanup_old_tasks()

    with update_tasks_lock:
        # 检查是否已有正在运行的任务
        if user_id in update_tasks:
            task = update_tasks[user_id]
            if task["status"] == "running":
                return jsonify(
                    {
                        "success": False,
                        "error": "更新正在进行中，请稍后再试",
                        "status": "running",
                    }
                ), 429

    try:
        # 启动后台线程执行更新
        # 使用包装函数捕获所有异常
        def wrapped_update_task(uid):
            try:
                run_update_task(uid)
            except Exception as e:
                import traceback

                print(f"[包装线程] 捕获到未处理的异常: {e}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
            finally:
                print(f"[包装线程] 线程即将结束: {uid}")

        thread = threading.Thread(
            target=wrapped_update_task, args=(user_id,), name=f"UpdateThread-{user_id}"
        )
        thread.daemon = True

        print(f"[API] 启动更新线程: {thread.name}, 守护={thread.daemon}")
        thread.start()

        return jsonify(
            {
                "success": True,
                "message": "更新任务已启动，正在后台运行中",
                "status": "started",
                "thread_name": thread.name,
            }
        )

    except Exception as e:
        print(f"[API] 启动更新线程失败: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc(file=sys.stderr)
        return jsonify({"success": False, "error": str(e)}), 500


# API: 查询更新状态
@app.route("/api/update-status", methods=["GET"])
@login_required
def api_get_update_status():
    """获取当前更新任务状态"""
    user_id = get_current_user_id()

    with update_tasks_lock:
        if user_id not in update_tasks:
            return jsonify(
                {"success": True, "status": "idle", "message": "没有正在进行的更新任务"}
            )

        task = update_tasks[user_id]
        response = {
            "success": True,
            "status": task["status"],
            "message": task.get("message", ""),
            "started_at": task.get("started_at").isoformat()
            if task.get("started_at")
            else None,
        }

        if task["status"] == "completed":
            response["result"] = task.get("result", {})
            response["completed_at"] = (
                task.get("completed_at").isoformat()
                if task.get("completed_at")
                else None
            )
        elif task["status"] == "failed":
            response["error"] = task.get("result", {}).get("error", "未知错误")
            response["completed_at"] = (
                task.get("completed_at").isoformat()
                if task.get("completed_at")
                else None
            )

        return jsonify(response)


@app.route("/api/stats")
@login_required
def api_get_stats():
    """获取系统统计"""
    user_id = get_current_user_id()

    # 获取该用户所有关键词组的文献总数
    user_groups = keyword_group_manager.get_user_groups(user_id)
    user_keywords = []
    for group in user_groups:
        user_keywords.extend(group.get("keywords", []))

    # 如果没有关键词组，从用户 preferences 中获取关键词（向后兼容）
    if not user_keywords:
        user = system.user_manager.get_user(user_id)
        if user and user.get("preferences"):
            user_keywords = user["preferences"].get("keywords", [])

    user_keywords = list(set(user_keywords))

    # 计算匹配的文献数量
    # 从数据库获取所有文献并实时筛选
    all_papers = system.cache.get_all_papers()
    scored_papers = []
    for paper in all_papers:
        score = system.push_engine._calculate_paper_score(paper, user_keywords)
        if score > 0:
            scored_papers.append(paper)
    user_total_papers = len(scored_papers)

    # 添加用户个人统计
    user_stats = system.push_engine.get_user_stats(user_id)

    return jsonify(
        {"success": True, "total_papers": user_total_papers, "user": user_stats}
    )


# API: 分析待处理文献
@app.route("/api/analyze-pending", methods=["POST"])
@login_required
def api_analyze_pending():
    user_id = get_current_user_id()

    user = system.user_manager.get_user(user_id)
    if not user:
        return jsonify({"success": False, "error": "用户不存在"}), 404

    user_keywords = user.get("keywords", [])

    if not user_keywords:
        return jsonify({"success": False, "error": "用户未设置关键词"})

    try:
        # 获取用户专属分析器
        user_analyzer = system.get_user_analyzer(user_id)

        # 从缓存获取文献
        paper_hashes = system.cache.find_papers_by_keywords(user_keywords)
        papers = system.cache.batch_get_papers(paper_hashes)

        # 分析未分析的文献
        analyzed_count = 0
        for paper in papers:
            if not paper.get("is_analyzed", False):
                # 调用用户专属分析器
                analysis = user_analyzer.analyze_paper(
                    paper.get("title", ""), paper.get("abstract", "")
                )

                if analysis and not analysis.get("error"):
                    # 翻译摘要（使用用户专属分析器）
                    abstract = paper.get("abstract", "")
                    abstract_cn = ""
                    if abstract and len(abstract) > 50:
                        abstract_cn = user_analyzer.translate_abstract(abstract)

                    # 确保所有值为字符串（处理元组和嵌套结构）
                    def to_str(v):
                        if v is None:
                            return ""
                        if isinstance(v, (tuple, list)):
                            if len(v) == 0:
                                return ""
                            return to_str(v[0])
                        if isinstance(v, dict):
                            for k in [
                                "main_findings",
                                "innovations",
                                "limitations",
                                "future_directions",
                                "abstract_cn",
                            ]:
                                if k in v and v[k]:
                                    return to_str(v[k])
                            return str(v)
                        return str(v) if v else ""

                    # 缓存分析结果
                    paper_hash = paper.get("hash")
                    if paper_hash:
                        system.cache.cache_analysis(
                            paper.get("title", ""),
                            abstract,
                            {
                                "main_findings": to_str(
                                    analysis.get("main_findings", "")
                                ),
                                "innovations": to_str(analysis.get("innovations", "")),
                                "limitations": to_str(analysis.get("limitations", "")),
                                "future_directions": to_str(
                                    analysis.get("future_directions", "")
                                ),
                                "abstract_cn": to_str(abstract_cn),
                            },
                            paper_hash=paper_hash,
                        )

                    # 同时更新文献缓存中的分析结果
                    paper_hash = paper.get("hash")
                    if paper_hash and paper_hash in system.cache.papers_cache:
                        system.cache.papers_cache[paper_hash]["is_analyzed"] = True
                        system.cache.papers_cache[paper_hash]["main_findings"] = to_str(
                            analysis.get("main_findings", "")
                        )
                        system.cache.papers_cache[paper_hash]["innovations"] = to_str(
                            analysis.get("innovations", "")
                        )
                        system.cache.papers_cache[paper_hash]["limitations"] = to_str(
                            analysis.get("limitations", "")
                        )
                        system.cache.papers_cache[paper_hash]["future_directions"] = (
                            to_str(analysis.get("future_directions", ""))
                        )
                        system.cache.papers_cache[paper_hash]["abstract_cn"] = to_str(
                            abstract_cn
                        )

                    analyzed_count += 1

        return jsonify({"success": True, "analyzed_count": analyzed_count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# API: 分析单篇文献 (V2.6 异步版本)
@app.route("/api/analyze-paper", methods=["POST"])
@login_required
@limiter.limit("10 per minute")
def api_analyze_paper():
    """分析单篇文献 - V2.6 支持异步队列"""
    user_id = get_current_user_id()
    data = request.get_json()
    paper_hash = data.get("paper_hash")
    # V2.6: 新增 async 参数，支持同步或异步模式
    async_mode = data.get("async", True)  # 默认异步模式

    if not paper_hash:
        return jsonify({"success": False, "error": "缺少paper_hash参数"})

    try:
        # 获取文献
        paper = system.cache.get_paper(paper_hash)
        if not paper:
            return jsonify({"success": False, "error": "文献不存在"})

        title = paper.get("title", "")
        abstract = paper.get("abstract", "")

        if not title or not abstract:
            return jsonify({"success": False, "error": "文献标题或摘要为空"})

        # 检查是否已有缓存分析
        cached = system.cache.get_cached_analysis(title, abstract)
        if cached:
            # 更新paper表
            paper.update(cached)
            paper["is_analyzed"] = True

            # 保存到数据库
            system.cache.cache_analysis(title, abstract, cached, paper_hash=paper_hash)

            return jsonify(
                {
                    "success": True,
                    "analyzed": False,
                    "message": "已有缓存分析结果",
                    "analysis": cached,
                }
            )

        # V2.6: 异步分析模式
        if async_mode:
            # 导入异步队列
            from core.async_queue import get_analysis_queue

            task_id = f"analyze_{user_id}_{paper_hash}"

            # 检查是否已在队列中
            queue = get_analysis_queue(max_workers=2)
            status = queue.get_status(task_id)

            if status and status["status"] in ["pending", "running"]:
                return jsonify(
                    {
                        "success": True,
                        "async": True,
                        "task_id": task_id,
                        "status": status["status"],
                        "message": "分析任务已在队列中",
                    }
                )

            # 获取用户分析器配置
            user_analyzer = system.get_user_analyzer(user_id)

            # 定义分析任务函数
            def do_analysis(analyzer, title, abstract, paper_hash):
                try:
                    # 分析文献
                    analysis = analyzer.analyze_paper(title, abstract)

                    if not analysis or analysis.get("error"):
                        return {"error": analysis.get("error", "分析失败")}

                    # 翻译摘要
                    abstract_cn = ""
                    if abstract and len(abstract) > 50:
                        abstract_cn = analyzer.translate_abstract(abstract)

                    # 确保值为字符串
                    def to_str(v):
                        if v is None:
                            return ""
                        if isinstance(v, (tuple, list)):
                            if len(v) == 0:
                                return ""
                            return to_str(v[0])
                        if isinstance(v, dict):
                            for k in [
                                "main_findings",
                                "innovations",
                                "limitations",
                                "future_directions",
                                "abstract_cn",
                            ]:
                                if k in v and v[k]:
                                    return to_str(v[k])
                            return str(v)
                        return str(v) if v else ""

                    result = {
                        "main_findings": to_str(analysis.get("main_findings", "")),
                        "innovations": to_str(analysis.get("innovations", "")),
                        "limitations": to_str(analysis.get("limitations", "")),
                        "future_directions": to_str(
                            analysis.get("future_directions", "")
                        ),
                        "abstract_cn": to_str(abstract_cn)
                        if not abstract_cn.startswith("翻译失败")
                        else "",
                    }

                    # 保存到缓存
                    from core.cache_manager import SmartCache

                    cache = SmartCache()
                    cache.cache_analysis(title, abstract, result, paper_hash=paper_hash)

                    return result
                except Exception as e:
                    return {"error": str(e)}

            # 提交异步任务
            result = queue.submit(
                task_id=task_id,
                func=do_analysis,
                args=(user_analyzer, title, abstract, paper_hash),
                priority=5,
            )

            if result["success"]:
                return jsonify(
                    {
                        "success": True,
                        "async": True,
                        "task_id": task_id,
                        "status": "submitted",
                        "message": "分析任务已提交，请稍后查询结果",
                    }
                )
            else:
                return jsonify(
                    {"success": False, "error": result.get("error", "提交任务失败")}
                )

        else:
            # 同步模式（兼容旧版本）
            user_analyzer = system.get_user_analyzer(user_id)
            analysis = user_analyzer.analyze_paper(title, abstract)

            if not analysis or analysis.get("error"):
                return jsonify(
                    {"success": False, "error": analysis.get("error", "分析失败")}
                )

            # 翻译摘要
            abstract_cn = ""
            if abstract and len(abstract) > 50:
                abstract_cn = user_analyzer.translate_abstract(abstract)

            # 确保值为字符串
            def to_str(v):
                if v is None:
                    return ""
                if isinstance(v, (tuple, list)):
                    if len(v) == 0:
                        return ""
                    return to_str(v[0])
                if isinstance(v, dict):
                    for k in [
                        "main_findings",
                        "innovations",
                        "limitations",
                        "future_directions",
                        "abstract_cn",
                    ]:
                        if k in v and v[k]:
                            return to_str(v[k])
                    return str(v)
                return str(v) if v else ""

            result = {
                "main_findings": to_str(analysis.get("main_findings", "")),
                "innovations": to_str(analysis.get("innovations", "")),
                "limitations": to_str(analysis.get("limitations", "")),
                "future_directions": to_str(analysis.get("future_directions", "")),
                "abstract_cn": to_str(abstract_cn)
                if not abstract_cn.startswith("翻译失败")
                else "",
            }

            # 保存到缓存和数据库
            system.cache.cache_analysis(title, abstract, result, paper_hash=paper_hash)

            return jsonify({"success": True, "analyzed": True, "analysis": result})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# API: 查询分析任务状态 (V2.6 新增)
@app.route("/api/analyze-status/<task_id>")
@login_required
def api_analyze_status(task_id):
    """查询异步分析任务状态"""
    try:
        from core.async_queue import get_analysis_queue

        queue = get_analysis_queue()
        status = queue.get_status(task_id)

        if not status:
            return jsonify({"success": False, "error": "任务不存在"}), 404

        return jsonify(
            {
                "success": True,
                "task_id": task_id,
                "status": status["status"],
                "result": status.get("result"),
                "error": status.get("error"),
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/user/auto-update-settings", methods=["GET"])
@login_required
def api_get_auto_update_settings():
    """获取用户自动更新设置"""
    user_id = get_current_user_id()

    try:
        settings = auto_update_service.get_user_schedule_info(user_id)
        settings["recommended_intervals"] = (
            auto_update_service.get_recommended_intervals()
        )

        return jsonify({"success": True, "settings": settings})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/user/auto-update-settings", methods=["PUT"])
@login_required
def api_save_auto_update_settings():
    """保存用户自动更新设置"""
    user_id = get_current_user_id()
    data = request.get_json()

    if data is None:
        return jsonify({"success": False, "error": "缺少请求数据"}), 400

    enabled = data.get("enabled", False)
    interval_days = data.get("interval_days", 2)

    try:
        # 更新调度
        auto_update_service.update_user_schedule(user_id, enabled, interval_days)

        # 保存到用户 preferences
        system.user_manager.update_preferences(
            user_id,
            {
                "auto_update_enabled": enabled,
                "auto_update_interval_days": interval_days,
            },
        )

        return jsonify({"success": True, "message": "自动更新设置已保存"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/user/last-update-info")
@login_required
def api_get_last_update_info():
    """获取用户最后更新信息"""
    user_id = get_current_user_id()

    try:
        info = auto_update_service.get_user_schedule_info(user_id)

        return jsonify(
            {
                "success": True,
                "last_update_at": info.get("last_update_at"),
                "last_update_result": info.get("last_update_result"),
                "auto_update_enabled": info.get("enabled", False),
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/user/all-saved-papers")
@login_required
def api_get_all_saved_papers():
    """获取用户所有收藏的文献（跨所有组）"""
    user_id = get_current_user_id()

    try:
        # 获取所有收藏的文献哈希
        saved_hashes = keyword_group_manager.get_all_saved_papers_for_user(user_id)

        if not saved_hashes:
            return jsonify(
                {"success": True, "papers": [], "saved_hashes": [], "total": 0}
            )

        # 从缓存获取文献详情
        papers = []
        missing_hashes = []
        for paper_hash in saved_hashes:
            paper = system.cache.get_cached_paper(paper_hash)
            if paper:
                # 标记为已收藏
                paper_copy = paper.copy()
                paper_copy["is_saved"] = True
                papers.append(paper_copy)
            else:
                # 记录缺失的文献
                missing_hashes.append(paper_hash)

        return jsonify(
            {
                "success": True,
                "papers": papers,
                "saved_hashes": saved_hashes,
                "missing_hashes": missing_hashes,
                "total": len(saved_hashes),
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# 健康检查
@app.route("/api/health")
def api_health():
    """健康检查"""
    return jsonify(
        {"status": "healthy", "version": "2.0", "timestamp": datetime.now().isoformat()}
    )


if __name__ == "__main__":
    host = os.getenv("WEB_HOST", "0.0.0.0")
    port = int(os.getenv("WEB_PORT", "5000"))
    debug = os.getenv("WEB_DEBUG", "True").lower() == "true"

    print(f"\n{'=' * 60}")
    print(f"V2 文献推送系统启动")
    print(f"访问地址: http://localhost:{port}")
    print(f"{'=' * 60}\n")

    app.run(host=host, port=port, debug=debug)
