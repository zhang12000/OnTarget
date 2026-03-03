#!/usr/bin/env python3
"""
简单SQLite数据库管理器 - 无需SQLAlchemy
使用原生sqlite3模块
"""

import sqlite3
import os
import json
from datetime import datetime

class SimpleDatabase:
    """简单的SQLite数据库管理器"""
    
    def __init__(self, db_path='data/literature.db'):
        # 转换为绝对路径
        if not os.path.isabs(db_path):
            # 获取项目根目录（simple_db.py 在 models/ 目录下）
            current_file = os.path.abspath(__file__)
            project_root = os.path.dirname(os.path.dirname(current_file))
            db_path = os.path.join(project_root, db_path)
        
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        # 确保目录存在
        db_dir = os.path.dirname(self.db_path)
        
        if db_dir:
            try:
                os.makedirs(db_dir, exist_ok=True)
            except Exception as e:
        
        # 连接数据库（会自动创建文件）
        try:
            conn = sqlite3.connect(self.db_path)
        except Exception as e:
            raise
        cursor = conn.cursor()
        
        # 创建用户表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                security_question TEXT,
                security_answer_hash TEXT,
                security_answer_salt TEXT,
                is_active INTEGER DEFAULT 1,
                is_admin INTEGER DEFAULT 0,
                created_at TEXT,
                last_login TEXT,
                preferences TEXT,
                avatar TEXT
            )
        ''')
        
        # 创建会话表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT,
                expires_at TEXT,
                ip_address TEXT,
                user_agent TEXT
            )
        ''')
        
        # 创建关键词组表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS keyword_groups (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                icon TEXT DEFAULT '🔬',
                color TEXT DEFAULT '#5a9a8f',
                keywords TEXT,
                match_mode TEXT DEFAULT 'any',
                min_match_score REAL DEFAULT 0.3,
                is_active INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        
        # 创建文献表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS papers (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                abstract TEXT,
                abstract_cn TEXT,
                authors TEXT,
                journal TEXT,
                pub_date TEXT,
                doi TEXT,
                pmid TEXT,
                url TEXT,
                source TEXT,
                main_findings TEXT,
                innovations TEXT,
                limitations TEXT,
                future_directions TEXT,
                is_analyzed INTEGER DEFAULT 0,
                impact_factor REAL,
                citations INTEGER DEFAULT 0,
                score REAL DEFAULT 0.0,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        
        # 创建搜索缓存表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS search_cache (
                id TEXT PRIMARY KEY,
                keywords TEXT,
                days_back INTEGER,
                paper_ids TEXT,
                created_at TEXT,
                expires_at TEXT
            )
        ''')
        
        # 创建分析缓存表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS analysis_cache (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                abstract TEXT,
                main_findings TEXT,
                innovations TEXT,
                limitations TEXT,
                future_directions TEXT,
                abstract_cn TEXT,
                created_at TEXT
            )
        ''')
        
        # 创建关键词索引表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS keyword_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                paper_id TEXT NOT NULL
            )
        ''')
        
        # 创建用户文献关联表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                paper_id TEXT NOT NULL,
                is_saved INTEGER DEFAULT 0,
                is_viewed INTEGER DEFAULT 0,
                viewed_at TEXT,
                saved_at TEXT
            )
        ''')
        
        # 创建组内收藏表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS group_saved_papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL,
                paper_id TEXT NOT NULL,
                saved_at TEXT
            )
        ''')
        
        # 创建组内阅读表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS group_viewed_papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL,
                paper_id TEXT NOT NULL,
                viewed_at TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        
        # 数据库迁移：添加缺失的列
        self._migrate_add_columns()
        
        print(f"✅ 数据库初始化完成: {self.db_path}")
    
    def _migrate_add_columns(self):
        """数据库迁移：添加缺失的列"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 检查 users 表是否有 avatar 列
        cursor.execute("PRAGMA table_info(users)")
        columns = [row['name'] for row in cursor.fetchall()]
        
        if 'avatar' not in columns:
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN avatar TEXT")
                print("✅ 数据库迁移: 已添加 avatar 列")
            except Exception as e:
                print(f"⚠️ 添加 avatar 列失败: {e}")
        
        if 'preferences' not in columns:
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN preferences TEXT")
                print("✅ 数据库迁移: 已添加 preferences 列")
            except Exception as e:
                print(f"⚠️ 添加 preferences 列失败: {e}")
        
        conn.commit()
        conn.close()
    
    def get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def execute(self, query, params=()):
        """执行SQL语句"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        lastrowid = cursor.lastrowid
        conn.close()
        return lastrowid
    
    def fetchone(self, query, params=()):
        """查询单条记录"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def fetchall(self, query, params=()):
        """查询多条记录"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_stats(self):
        """获取数据库统计信息"""
        tables = ['users', 'sessions', 'keyword_groups', 'papers', 
                  'search_cache', 'analysis_cache', 'keyword_index']
        stats = {}
        for table in tables:
            try:
                result = self.fetchone(f"SELECT COUNT(*) as count FROM {table}")
                stats[table] = result['count'] if result else 0
            except:
                stats[table] = 0
        return stats

# 全局数据库实例
_db_instance = None

def get_db(db_path=None):
    """获取全局数据库实例
    
    Args:
        db_path: 数据库路径，默认使用配置的默认路径
    """
    global _db_instance
    if _db_instance is None or (db_path and _db_instance.db_path != db_path):
        if db_path:
            _db_instance = SimpleDatabase(db_path)
        else:
            # 使用绝对路径，避免相对路径问题
            # 从当前文件位置往上找，找到项目根目录
            current_file = os.path.abspath(__file__)
            # simple_db.py 在 models/ 目录下，项目根目录是 models/ 的父目录
            project_root = os.path.dirname(os.path.dirname(current_file))
            default_path = os.path.join(project_root, 'data', 'literature.db')
            _db_instance = SimpleDatabase(default_path)
    return _db_instance

if __name__ == '__main__':
    db = SimpleDatabase()
    stats = db.get_stats()
    print("\n数据库统计:")
    for table, count in stats.items():
        print(f"  {table}: {count} 条记录")
