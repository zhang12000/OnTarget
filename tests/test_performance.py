#!/usr/bin/env python3
"""
性能优化测试 - 验证性能改进相关的代码变更
"""

import sys
import os
import re
import time
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v1.fetcher import PaperFetcher
from v1.impact_factor import ImpactFactorFetcher, _RE_PARENS, _RE_BRACKETS, _RE_TRAILING_COLON


class TestKeywordMatchPerformance:
    """关键词匹配性能测试"""

    def setup_method(self):
        self.fetcher = PaperFetcher(pubmed_email='test@test.com')

    def test_compiled_patterns_cache_exists(self):
        """测试编译正则缓存已初始化"""
        assert hasattr(self.fetcher, '_compiled_patterns')
        assert isinstance(self.fetcher._compiled_patterns, dict)

    def test_short_keyword_compiles_pattern_once(self):
        """测试短关键词仅编译一次正则"""
        text = "This is about RNA expression"
        keywords = ['RNA']

        # 第一次调用
        result1 = self.fetcher._check_keywords_match(text, keywords)
        assert result1 is True
        assert 'rna' in self.fetcher._compiled_patterns

        # 第二次调用应复用已编译的正则
        compiled_pattern = self.fetcher._compiled_patterns['rna']
        result2 = self.fetcher._check_keywords_match(text, keywords)
        assert result2 is True
        # 确认同一个编译对象被复用
        assert self.fetcher._compiled_patterns['rna'] is compiled_pattern

    def test_keyword_match_correctness(self):
        """测试关键词匹配结果不受优化影响"""
        # 长关键词 - 直接匹配
        assert self.fetcher._check_keywords_match("cancer research advances", ["cancer"]) is True
        assert self.fetcher._check_keywords_match("weather patterns", ["cancer"]) is False

        # 短关键词 - 需要完整词边界匹配
        assert self.fetcher._check_keywords_match("RNA expression", ["RNA"]) is True
        assert self.fetcher._check_keywords_match("crane bird study", ["RNA"]) is False

        # 连字符变体
        assert self.fetcher._check_keywords_match("TDP-43 protein study", ["TDP43"]) is True
        assert self.fetcher._check_keywords_match("TDP43 protein study", ["TDP-43"]) is True

        # 空格变连字符
        assert self.fetcher._check_keywords_match("cell-death pathway", ["cell death"]) is True

    def test_keyword_match_performance(self):
        """测试关键词匹配性能（编译缓存应减少执行时间）"""
        text = "This is a long text about cancer research and immunotherapy treatment methods " * 10
        keywords = ['RNA', 'DNA', 'PCR']

        # 预热
        self.fetcher._check_keywords_match(text, keywords)

        # 计时执行多次
        start = time.time()
        for _ in range(1000):
            self.fetcher._check_keywords_match(text, keywords)
        elapsed = time.time() - start

        # 1000次调用应该在1秒内完成
        assert elapsed < 1.0, f"1000次关键词匹配耗时 {elapsed:.2f}s，超过1秒"


class TestImpactFactorRegex:
    """影响因子正则预编译测试"""

    def test_precompiled_patterns_exist(self):
        """测试预编译正则已在模块级别定义"""
        assert isinstance(_RE_PARENS, re.Pattern)
        assert isinstance(_RE_BRACKETS, re.Pattern)
        assert isinstance(_RE_TRAILING_COLON, re.Pattern)

    def test_regex_cleanup_correctness(self):
        """测试正则清理结果的正确性"""
        # 括号清理
        assert _RE_PARENS.sub('', 'advanced science (weinheim)').strip() == 'advanced science'
        assert _RE_PARENS.sub('', 'nature (london, england)').strip() == 'nature'

        # 方括号清理
        assert _RE_BRACKETS.sub('', 'journal [online]').strip() == 'journal'

        # 末尾冒号清理
        assert _RE_TRAILING_COLON.sub('', 'journal name :').strip() == 'journal name'
        assert _RE_TRAILING_COLON.sub('', 'journal name').strip() == 'journal name'


class TestBatchGetPapers:
    """批量获取文献测试"""

    def setup_method(self):
        from core.cache_manager import SmartCache
        self.cache = SmartCache(db_path=os.path.join(tempfile.mkdtemp(), 'test_perf.db'))

    def test_batch_get_empty_list(self):
        """测试空列表输入"""
        result = self.cache.batch_get_papers([])
        assert result == []

    def test_batch_get_nonexistent_papers(self):
        """测试获取不存在的文献"""
        result = self.cache.batch_get_papers(['nonexistent_hash_1', 'nonexistent_hash_2'])
        assert result == []

    def test_batch_get_preserves_order(self):
        """测试批量获取保持原始顺序"""
        # 缓存几篇文献
        papers = []
        hashes = []
        for i in range(5):
            paper = {
                'title': f'Test Paper {i}',
                'abstract': f'Abstract {i}',
                'doi': f'10.1234/test{i}',
                'authors': ['Author A'],
                'journal': 'Test Journal',
                'publication_date': '2024-01-01',
                'url': f'https://example.com/{i}',
                'source': 'pubmed',
                'paper_type': 'research'
            }
            paper_hash = self.cache._get_paper_hash(paper)
            paper['hash'] = paper_hash
            self.cache.cache_paper(paper)
            papers.append(paper)
            hashes.append(paper_hash)

        # 以逆序获取，验证顺序保留
        reversed_hashes = list(reversed(hashes))
        result = self.cache.batch_get_papers(reversed_hashes)

        assert len(result) == 5
        for i, paper in enumerate(result):
            assert paper['title'] == f'Test Paper {4 - i}'


class TestCleanupOptimization:
    """清理缓存优化测试"""

    def setup_method(self):
        from core.cache_manager import SmartCache
        self.cache = SmartCache(db_path=os.path.join(tempfile.mkdtemp(), 'test_cleanup.db'))

    def test_cleanup_returns_counts(self):
        """测试清理返回正确的删除数量"""
        result = self.cache.cleanup_old_cache(days=30)

        assert 'removed_papers' in result
        assert 'removed_searches' in result
        assert 'removed_analysis' in result
        assert isinstance(result['removed_papers'], int)
        assert isinstance(result['removed_searches'], int)
        assert isinstance(result['removed_analysis'], int)

    def test_cleanup_empty_db(self):
        """测试清理不出错"""
        result = self.cache.cleanup_old_cache(days=0)

        # 验证返回的是整数计数，即使有或没有数据
        assert isinstance(result['removed_papers'], int)
        assert isinstance(result['removed_searches'], int)
        assert isinstance(result['removed_analysis'], int)
        assert result['removed_papers'] >= 0
        assert result['removed_searches'] >= 0
        assert result['removed_analysis'] >= 0


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
