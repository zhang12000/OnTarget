#!/usr/bin/env python3
"""
缓存管理器测试 - 验证 find_papers_by_keywords 和 cleanup_old_cache 的行为
"""

import sys
import os
import tempfile
import shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, timedelta
import models.database as db_module
from models.database import DatabaseManager, Paper, KeywordIndex


def _make_isolated_cache(tmp_path):
    """
    创建一个完全隔离的 SmartCache 实例：
    - 每个测试使用独立的临时 SQLite 文件
    - 重置全局 _db_manager 单例，确保各测试之间互不影响
    """
    db_file = os.path.join(tmp_path, 'test_cache.db')
    # 重置数据库管理器单例，使新路径生效
    db_module._db_manager = None
    from core.cache_manager import SmartCache
    cache = SmartCache(db_path=db_file)
    return cache, db_file


def _insert_paper_with_keyword(db_file: str, paper_id: str, keyword: str,
                                created_at: datetime = None):
    """向测试数据库插入 Paper 和对应的 KeywordIndex 行"""
    mgr = DatabaseManager(db_file)
    db = mgr.get_session()
    try:
        if created_at is None:
            created_at = datetime.now()
        paper = Paper(
            id=paper_id,
            title=f'Title {paper_id}',
            abstract='abstract',
            created_at=created_at,
        )
        db.add(paper)
        db.flush()
        kw = KeywordIndex(paper_id=paper_id, keyword=keyword)
        db.add(kw)
        db.commit()
    finally:
        db.close()
        mgr.close()


class TestFindPapersByKeywords:
    """验证 find_papers_by_keywords 使用合并 OR 查询后的正确性"""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.cache, self.db_file = _make_isolated_cache(self.tmp)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- exact match ----

    def test_exact_match_returns_paper(self):
        """精确匹配应返回对应文献"""
        _insert_paper_with_keyword(self.db_file, 'paper1', 'cancer')
        result = self.cache.find_papers_by_keywords(['cancer'])
        assert 'paper1' in result

    def test_exact_match_score_highest(self):
        """精确匹配的文献应排在部分匹配之前"""
        _insert_paper_with_keyword(self.db_file, 'exact', 'cancer')
        _insert_paper_with_keyword(self.db_file, 'prefix', 'cancer therapy')
        _insert_paper_with_keyword(self.db_file, 'contains', 'advanced cancer therapy')
        result = self.cache.find_papers_by_keywords(['cancer'])
        assert result[0] == 'exact'

    # ---- prefix match ----

    def test_prefix_match_returns_paper(self):
        """开头匹配（前缀）应返回文献"""
        _insert_paper_with_keyword(self.db_file, 'paper2', 'cancer therapy')
        result = self.cache.find_papers_by_keywords(['cancer'])
        assert 'paper2' in result

    # ---- contains match ----

    def test_contains_match_returns_paper(self):
        """包含匹配应返回文献"""
        _insert_paper_with_keyword(self.db_file, 'paper3', 'advanced cancer therapy')
        result = self.cache.find_papers_by_keywords(['cancer'])
        assert 'paper3' in result

    # ---- no match ----

    def test_no_match_returns_empty(self):
        """无匹配时应返回空列表"""
        _insert_paper_with_keyword(self.db_file, 'paper4', 'unrelated topic')
        result = self.cache.find_papers_by_keywords(['cancer'])
        assert result == []

    # ---- empty input ----

    def test_empty_keywords_returns_empty(self):
        """空关键词列表应返回空列表"""
        result = self.cache.find_papers_by_keywords([])
        assert result == []

    # ---- case insensitivity ----

    def test_case_insensitive_match(self):
        """搜索不应区分大小写"""
        _insert_paper_with_keyword(self.db_file, 'paper5', 'cancer')
        result = self.cache.find_papers_by_keywords(['CANCER'])
        assert 'paper5' in result

    # ---- limit ----

    def test_limit_respected(self):
        """limit 参数应限制返回数量"""
        for i in range(5):
            _insert_paper_with_keyword(self.db_file, f'p{i}', 'cancer')
        result = self.cache.find_papers_by_keywords(['cancer'], limit=3)
        assert len(result) <= 3


class TestCleanupOldCache:
    """验证 cleanup_old_cache 批量删除的正确性"""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.cache, self.db_file = _make_isolated_cache(self.tmp)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _count_papers(self):
        mgr = DatabaseManager(self.db_file)
        db = mgr.get_session()
        try:
            return db.query(Paper).count()
        finally:
            db.close()
            mgr.close()

    def test_old_papers_are_removed(self):
        """超过指定天数的文献应被删除"""
        old_date = datetime.now() - timedelta(days=40)
        _insert_paper_with_keyword(self.db_file, 'old_paper', 'kw', created_at=old_date)
        assert self._count_papers() == 1
        result = self.cache.cleanup_old_cache(days=30)
        assert result['removed_papers'] == 1
        assert self._count_papers() == 0

    def test_recent_papers_are_kept(self):
        """未过期的文献不应被删除"""
        _insert_paper_with_keyword(self.db_file, 'new_paper', 'kw')
        assert self._count_papers() == 1
        result = self.cache.cleanup_old_cache(days=30)
        assert result['removed_papers'] == 0
        assert self._count_papers() == 1

    def test_returns_correct_counts(self):
        """cleanup_old_cache 应返回正确的删除计数"""
        old_date = datetime.now() - timedelta(days=60)
        for i in range(3):
            _insert_paper_with_keyword(self.db_file, f'old{i}', 'kw', created_at=old_date)
        result = self.cache.cleanup_old_cache(days=30)
        assert result['removed_papers'] == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
