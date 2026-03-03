#!/usr/bin/env python3
"""
数据库模型定义 - SQLAlchemy 1.3 兼容版本
使用 Text 存储 JSON 数据，手动序列化/反序列化
"""

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, Float, ForeignKey, Index, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.types import TypeDecorator
from datetime import datetime
import json
import os

Base = declarative_base()

class JSONColumn(TypeDecorator):
    """自定义JSON列类型，兼容SQLAlchemy 1.3"""
    impl = Text
    
    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value)
    
    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return json.loads(value)
        except:
            return value

class User(Base):
    """用户表"""
    __tablename__ = 'users'
    
    id = Column(String(64), primary_key=True)
    username = Column(String(100), nullable=False, unique=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(128), nullable=False)
    password_salt = Column(String(64), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    last_login = Column(DateTime, nullable=True)
    
    # 偏好设置(JSON存储)
    preferences = Column(JSONColumn, default=dict)
    
    # 关系
    keyword_groups = relationship("KeywordGroup", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    user_papers = relationship("UserPaper", back_populates="user", cascade="all, delete-orphan")

class Session(Base):
    """会话表"""
    __tablename__ = 'sessions'
    
    id = Column(String(128), primary_key=True)
    user_id = Column(String(64), ForeignKey('users.id'), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime, nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(512), nullable=True)
    
    user = relationship("User", back_populates="sessions")

class KeywordGroup(Base):
    """关键词组表"""
    __tablename__ = 'keyword_groups'
    
    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey('users.id'), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(10), default='🔬')
    color = Column(String(10), default='#5a9a8f')
    keywords = Column(JSONColumn, default=list)
    match_mode = Column(String(10), default='any')
    min_match_score = Column(Float, default=0.3)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    user = relationship("User", back_populates="keyword_groups")
    saved_papers = relationship("GroupSavedPaper", back_populates="group", cascade="all, delete-orphan")
    viewed_papers = relationship("GroupViewedPaper", back_populates="group", cascade="all, delete-orphan")

class Paper(Base):
    """文献表"""
    __tablename__ = 'papers'
    
    id = Column(String(64), primary_key=True)
    title = Column(Text, nullable=False)
    abstract = Column(Text, nullable=True)
    abstract_cn = Column(Text, nullable=True)
    authors = Column(JSONColumn, default=list)
    journal = Column(String(500), nullable=True)
    pub_date = Column(String(20), nullable=True)
    doi = Column(String(200), nullable=True, index=True)
    pmid = Column(String(20), nullable=True, index=True)
    url = Column(String(1000), nullable=True)
    source = Column(String(50), nullable=True)
    
    # AI分析结果
    main_findings = Column(Text, nullable=True)
    innovations = Column(Text, nullable=True)
    limitations = Column(Text, nullable=True)
    future_directions = Column(Text, nullable=True)
    is_analyzed = Column(Boolean, default=False)
    
    # 元数据
    impact_factor = Column(Float, nullable=True)
    citations = Column(Integer, default=0)
    score = Column(Float, default=0.0)
    paper_type = Column(String(20), default='research')
    
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 索引
    __table_args__ = (
        Index('idx_papers_created', 'created_at'),
        Index('idx_papers_analyzed', 'is_analyzed'),
    )

class UserPaper(Base):
    """用户文献关联表"""
    __tablename__ = 'user_papers'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey('users.id'), nullable=False, index=True)
    paper_id = Column(String(64), ForeignKey('papers.id'), nullable=False, index=True)
    is_saved = Column(Boolean, default=False)
    is_viewed = Column(Boolean, default=False)
    viewed_at = Column(DateTime, nullable=True)
    saved_at = Column(DateTime, nullable=True)
    
    user = relationship("User", back_populates="user_papers")
    paper = relationship("Paper")

class GroupSavedPaper(Base):
    """组内收藏的文献"""
    __tablename__ = 'group_saved_papers'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(64), ForeignKey('keyword_groups.id'), nullable=False, index=True)
    paper_id = Column(String(64), ForeignKey('papers.id'), nullable=False, index=True)
    saved_at = Column(DateTime, default=datetime.now)
    
    group = relationship("KeywordGroup", back_populates="saved_papers")
    paper = relationship("Paper")

class GroupViewedPaper(Base):
    """组内阅读过的文献"""
    __tablename__ = 'group_viewed_papers'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(64), ForeignKey('keyword_groups.id'), nullable=False, index=True)
    paper_id = Column(String(64), ForeignKey('papers.id'), nullable=False, index=True)
    viewed_at = Column(DateTime, default=datetime.now)
    
    group = relationship("KeywordGroup", back_populates="viewed_papers")
    paper = relationship("Paper")

class SearchCache(Base):
    """搜索缓存表"""
    __tablename__ = 'search_cache'
    
    id = Column(String(64), primary_key=True)
    keywords = Column(JSONColumn, nullable=False)
    days_back = Column(Integer, nullable=False)
    paper_ids = Column(JSONColumn, default=list)
    created_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime, nullable=False)

class AnalysisCache(Base):
    """AI分析缓存表"""
    __tablename__ = 'analysis_cache'
    
    id = Column(String(64), primary_key=True)
    title = Column(Text, nullable=False)
    abstract = Column(Text, nullable=True)
    main_findings = Column(Text, nullable=True)
    innovations = Column(Text, nullable=True)
    limitations = Column(Text, nullable=True)
    future_directions = Column(Text, nullable=True)
    abstract_cn = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

class KeywordIndex(Base):
    """关键词索引表"""
    __tablename__ = 'keyword_index'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    keyword = Column(String(200), nullable=False, index=True)
    paper_id = Column(String(64), ForeignKey('papers.id'), nullable=False, index=True)
    
    paper = relationship("Paper")

class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, db_path='data/literature.db'):
        self.db_path = db_path
        self.engine = None
        self.Session = None
        self._init_database()
    
    def _init_database(self):
        """初始化数据库 - V2.6 启用 WAL 模式提升并发性能"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
        
        self.engine = create_engine(
            f'sqlite:///{self.db_path}',
            echo=False,
            connect_args={'check_same_thread': False}
        )
        
        # V2.6 优化：启用 WAL 模式，大幅提升并发写入性能
        # WAL 模式允许多个读取者和一个写入者同时访问数据库
        with self.engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA synchronous=NORMAL"))  # 平衡性能和安全性
            conn.execute(text("PRAGMA cache_size=-64000"))   # 64MB 页面缓存
            conn.execute(text("PRAGMA temp_store=MEMORY"))   # 临时表存储在内存
            conn.execute(text("PRAGMA mmap_size=268435456")) # 256MB 内存映射
        
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
    
    def get_session(self):
        """获取数据库会话"""
        return self.Session()
    
    def close(self):
        """关闭数据库连接"""
        if self.engine:
            self.engine.dispose()

_db_manager = None

def get_db_manager(db_path='data/literature.db'):
    """获取全局数据库管理器实例"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager(db_path)
    return _db_manager

def get_db_session(db_path='data/literature.db'):
    """获取数据库会话（快捷方式）"""
    return get_db_manager(db_path).get_session()
