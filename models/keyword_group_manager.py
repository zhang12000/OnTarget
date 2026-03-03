#!/usr/bin/env python3
"""
关键词组管理模块 - SQLite版本 (V2.3)
支持多组关键词和组独立数据
"""

import secrets
from datetime import datetime
from typing import Dict, List, Optional

from models.adapter import get_db_session, KeywordGroup, GroupSavedPaper, GroupViewedPaper

class KeywordGroupManager:
    """
    关键词组管理器
    管理用户的多组关键词，以及每个组的独立数据
    """
    
    def __init__(self, db_path='data/literature.db'):
        self.db_path = db_path
    
    def _get_session(self):
        """获取数据库会话"""
        return get_db_session(self.db_path)
    
    def create_group(self, user_id: str, name: str, keywords: List[str], 
                     icon: str = '🔬', color: str = '#5a9a8f',
                     description: str = '', match_mode: str = 'any',
                     min_match_score: float = 0.3) -> Dict:
        """
        创建新的关键词组
        
        Returns:
            {'success': True, 'group_id': 'kg_xxx'} or {'success': False, 'error': '...'}
        """
        if not name or not name.strip():
            return {'success': False, 'error': '组名称不能为空'}
        
        if not keywords or len(keywords) == 0:
            return {'success': False, 'error': '关键词不能为空'}
        
        # 清理关键词
        keywords = [k.strip() for k in keywords if k.strip()]
        keywords = list(set(keywords))  # 去重
        
        if len(keywords) == 0:
            return {'success': False, 'error': '关键词不能为空'}
        
        # 生成唯一ID
        group_id = f"kg_{int(datetime.now().timestamp())}_{secrets.token_hex(4)}"
        
        db = self._get_session()
        try:
            new_group = KeywordGroup(
                id=group_id,
                user_id=user_id,
                name=name.strip(),
                icon=icon,
                color=color,
                description=description,
                keywords=keywords,
                is_active=True,
                match_mode=match_mode,
                min_match_score=min_match_score,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            db.add(new_group)
            db.commit()
            
            return {
                'success': True,
                'group_id': group_id,
                'group': self._group_to_dict(new_group)
            }
            
        except Exception as e:
            db.rollback()
            return {'success': False, 'error': f'创建失败: {str(e)}'}
        finally:
            db.close()
    
    def update_group(self, user_id: str, group_id: str, updates: Dict) -> Dict:
        """
        更新关键词组
        
        Args:
            updates: 可以包含 name, icon, color, description, keywords, 
                    is_active, match_mode, min_match_score
        """
        db = self._get_session()
        try:
            group = db.query(KeywordGroup).filter_by(id=group_id, user_id=user_id).first()
            
            if not group:
                return {'success': False, 'error': '组不存在'}
            
            # 可更新的字段
            allowed_fields = ['name', 'icon', 'color', 'description', 
                             'keywords', 'is_active', 'match_mode', 'min_match_score']
            
            for field in allowed_fields:
                if field in updates:
                    if field == 'keywords':
                        # 清理关键词
                        keywords = [k.strip() for k in updates[field] if k.strip()]
                        keywords = list(set(keywords))
                        if len(keywords) == 0:
                            return {'success': False, 'error': '关键词不能为空'}
                        group.keywords = keywords
                    elif field == 'name':
                        if not updates[field] or not updates[field].strip():
                            return {'success': False, 'error': '组名称不能为空'}
                        group.name = updates[field].strip()
                    else:
                        setattr(group, field, updates[field])
            
            group.updated_at = datetime.now()
            
            # 显式调用 save 方法保存更改
            if hasattr(group, 'save'):
                group.save()
            
            db.commit()
            
            return {'success': True, 'group': self._group_to_dict(group)}
            
        except Exception as e:
            db.rollback()
            return {'success': False, 'error': f'更新失败: {str(e)}'}
        finally:
            db.close()
    
    def delete_group(self, user_id: str, group_id: str) -> Dict:
        """删除关键词组"""
        db = self._get_session()
        try:
            group = db.query(KeywordGroup).filter_by(id=group_id, user_id=user_id).first()
            
            if not group:
                return {'success': False, 'error': '组不存在'}
            
            db.delete(group)  # 级联删除关联数据
            db.commit()
            
            return {'success': True}
            
        except Exception as e:
            db.rollback()
            return {'success': False, 'error': f'删除失败: {str(e)}'}
        finally:
            db.close()
    
    def get_user_groups(self, user_id: str, include_inactive: bool = False) -> List[Dict]:
        """
        获取用户的所有关键词组
        
        Returns:
            按创建时间排序的组列表
        """
        db = self._get_session()
        try:
            query = db.query(KeywordGroup).filter_by(user_id=user_id)
            
            if not include_inactive:
                query = query.filter_by(is_active=True)
            
            groups = query.order_by("created_at DESC").all()
            
            result = []
            for group in groups:
                group_dict = self._group_to_dict(group)
                group_dict['stats'] = self._get_group_stats(user_id, group.id)
                result.append(group_dict)
            
            return result
            
        finally:
            db.close()
    
    def get_group(self, user_id: str, group_id: str) -> Optional[Dict]:
        """获取特定组的详细信息"""
        db = self._get_session()
        try:
            group = db.query(KeywordGroup).filter_by(id=group_id, user_id=user_id).first()
            
            if not group:
                return None
            
            group_dict = self._group_to_dict(group)
            group_dict['stats'] = self._get_group_stats(user_id, group_id)
            return group_dict
            
        finally:
            db.close()
    
    def _get_group_stats(self, user_id: str, group_id: str) -> Dict:
        """获取组的统计信息"""
        db = self._get_session()
        try:
            # 统计收藏的文献数（从数据库）
            saved_count = db.query(GroupSavedPaper).filter_by(group_id=group_id).count()
            viewed_count = db.query(GroupViewedPaper).filter_by(group_id=group_id).count()
            
            last_viewed = db.query(GroupViewedPaper).filter_by(group_id=group_id).first()
            
            # 处理 last_access 时间格式
            last_access = None
            if last_viewed and last_viewed.viewed_at:
                if hasattr(last_viewed.viewed_at, 'isoformat'):
                    last_access = last_viewed.viewed_at.isoformat()
                else:
                    # 已经是字符串格式
                    last_access = last_viewed.viewed_at
            
            return {
                'total_viewed': viewed_count,
                'total_saved': saved_count,
                'last_access': last_access
            }
        finally:
            db.close()
    
    def reorder_groups(self, user_id: str, group_order: List[str]) -> Dict:
        """
        重新排序用户的关键词组
        
        Args:
            group_order: 组ID列表，按期望的顺序排列
        """
        db = self._get_session()
        try:
            # 验证所有组ID都存在
            for group_id in group_order:
                group = db.query(KeywordGroup).filter_by(id=group_id, user_id=user_id).first()
                if not group:
                    return {'success': False, 'error': f'组不存在: {group_id}'}
            
            # 重新排序（通过修改created_at实现）
            current_time = datetime.now().timestamp()
            for i, group_id in enumerate(group_order):
                group = db.query(KeywordGroup).filter(
                    KeywordGroup.id == group_id
                ).first()
                # 越靠前时间戳越大（这样按时间倒序排列时会显示在前面）
                group.created_at = datetime.fromtimestamp(current_time - i)
            
            db.commit()
            return {'success': True}
            
        except Exception as e:
            db.rollback()
            return {'success': False, 'error': f'排序失败: {str(e)}'}
        finally:
            db.close()
    
    # ============ 组独立数据操作 ============
    
    def save_paper_to_group(self, user_id: str, group_id: str, paper_hash: str) -> Dict:
        """在特定组中收藏文献"""
        db = self._get_session()
        try:
            # 检查组是否存在
            group = db.query(KeywordGroup).filter_by(id=group_id, user_id=user_id).first()
            
            if not group:
                return {'success': False, 'error': '组不存在'}
            
            # 检查是否已收藏
            existing = db.query(GroupSavedPaper).filter_by(group_id=group_id, paper_id=paper_hash).first()
            
            if not existing:
                new_saved = GroupSavedPaper(
                    group_id=group_id,
                    paper_id=paper_hash,
                    saved_at=datetime.now().isoformat()
                )
                db.add(new_saved)
                db.commit()
            
            return {'success': True}
            
        except Exception as e:
            db.rollback()
            return {'success': False, 'error': f'收藏失败: {str(e)}'}
        finally:
            db.close()
    
    def unsave_paper_from_group(self, user_id: str, group_id: str, paper_hash: str) -> Dict:
        """取消收藏文献"""
        db = self._get_session()
        try:
            # 检查组是否存在
            group = db.query(KeywordGroup).filter_by(id=group_id, user_id=user_id).first()
            
            if not group:
                return {'success': False, 'error': '组不存在'}
            
            # 删除收藏记录
            saved = db.query(GroupSavedPaper).filter_by(group_id=group_id, paper_id=paper_hash).first()
            
            if saved:
                db.delete(saved)
                db.commit()
            
            return {'success': True}
            
        except Exception as e:
            db.rollback()
            return {'success': False, 'error': f'取消收藏失败: {str(e)}'}
        finally:
            db.close()
    
    def is_paper_saved_in_group(self, user_id: str, group_id: str, paper_hash: str) -> bool:
        """检查文献是否在特定组中已收藏"""
        db = self._get_session()
        try:
            # 检查组是否存在
            group = db.query(KeywordGroup).filter_by(id=group_id, user_id=user_id).first()
            
            if not group:
                return False
            
            saved = db.query(GroupSavedPaper).filter_by(group_id=group_id, paper_id=paper_hash).first()
            
            return saved is not None
            
        finally:
            db.close()
    
    def get_saved_papers_in_group(self, user_id: str, group_id: str) -> List[str]:
        """获取特定组中收藏的所有文献"""
        db = self._get_session()
        try:
            # 检查组是否存在
            group = db.query(KeywordGroup).filter_by(id=group_id, user_id=user_id).first()
            
            if not group:
                return []
            
            saved_papers = db.query(GroupSavedPaper).filter_by(
                group_id=group_id
            ).all()
            
            return [sp.paper_id for sp in saved_papers]
            
        finally:
            db.close()
    
    def get_all_saved_papers_for_user(self, user_id: str) -> List[str]:
        """
        获取用户所有组中收藏的所有文献（去重）
        用于优化前端加载，减少多次请求
        """
        db = self._get_session()
        try:
            # 获取用户的所有组ID
            groups = db.query(KeywordGroup).filter_by(user_id=user_id).all()
            group_ids = [g.id for g in groups]
            
            if not group_ids:
                return []
            
            # 使用原始 SQL 查询所有组的收藏
            # 构建占位符
            placeholders = ','.join(['?' for _ in group_ids])
            query = f"SELECT DISTINCT paper_id FROM group_saved_papers WHERE group_id IN ({placeholders})"
            
            # 执行查询
            from models.simple_db import get_db
            simple_db = get_db()
            results = simple_db.fetchall(query, tuple(group_ids))
            
            # 提取 paper_id
            unique_hashes = [row['paper_id'] for row in results] if results else []
            return unique_hashes
            
        finally:
            db.close()
    
    def mark_paper_viewed_in_group(self, user_id: str, group_id: str, paper_hash: str):
        """标记文献在特定组中已读"""
        db = self._get_session()
        try:
            # 检查组是否存在
            group = db.query(KeywordGroup).filter_by(id=group_id, user_id=user_id).first()
            
            if not group:
                return
            
            # 检查是否已记录
            existing = db.query(GroupViewedPaper).filter_by(group_id=group_id, paper_id=paper_hash).first()
            
            if not existing:
                new_viewed = GroupViewedPaper(
                    group_id=group_id,
                    paper_id=paper_hash,
                    viewed_at=datetime.now()
                )
                db.add(new_viewed)
                db.commit()
            
        except Exception as e:
            db.rollback()
        finally:
            db.close()
    
    def is_paper_viewed_in_group(self, user_id: str, group_id: str, paper_hash: str) -> bool:
        """检查文献在特定组中是否已读"""
        db = self._get_session()
        try:
            # 检查组是否存在
            group = db.query(KeywordGroup).filter_by(id=group_id, user_id=user_id).first()
            
            if not group:
                return False
            
            viewed = db.query(GroupViewedPaper).filter_by(group_id=group_id, paper_id=paper_hash).first()
            
            return viewed is not None
            
        finally:
            db.close()
    
    def update_group_access_time(self, user_id: str, group_id: str):
        """更新组的最后访问时间"""
        # 通过添加一条浏览记录来实现
        # 实际上最后一次浏览记录的时间就是最后访问时间
        pass
    
    # ============ 汇总Dashboard数据 ============
    
    def get_user_groups_summary(self, user_id: str) -> Dict:
        """
        获取用户所有组的汇总信息（用于Dashboard）
        """
        db = self._get_session()
        try:
            groups = db.query(KeywordGroup).filter_by(user_id=user_id).all()

            total_viewed = 0
            total_saved = 0
            active_count = 0

            summary_groups = []
            for group in groups:
                stats = self._get_group_stats(user_id, group.id)
                viewed = stats.get('total_viewed', 0)
                saved = stats.get('total_saved', 0)

                total_viewed += viewed
                total_saved += saved

                if group.is_active:
                    active_count += 1

                summary_groups.append({
                    'id': group.id,
                    'name': group.name,
                    'icon': group.icon or '🔬',
                    'color': group.color or '#5a9a8f',
                    'keywords_count': len(group.keywords or []),
                    'is_active': group.is_active,
                    'papers_viewed': viewed,
                    'papers_saved': saved,
                    'last_access': stats.get('last_access')
                })

            return {
                'total_groups': len(groups),
                'active_groups': active_count,
                'total_papers_viewed': total_viewed,
                'total_papers_saved': total_saved,
                'groups': summary_groups
            }

        finally:
            db.close()
    
    # ============ 数据迁移 ============
    
    def migrate_from_old_keywords(self, user_id: str, old_keywords: List[str]) -> Dict:
        """
        从旧版关键词列表迁移到新的组结构
        创建一个名为"我的关键词"的默认组
        """
        if not old_keywords:
            return {'success': True, 'message': '没有旧关键词需要迁移'}
        
        # 检查是否已经迁移过（通过检查是否有组）
        existing_groups = self.get_user_groups(user_id)
        if len(existing_groups) > 0:
            return {'success': True, 'message': '已经迁移过，跳过'}
        
        # 创建默认组
        result = self.create_group(
            user_id=user_id,
            name='我的关键词',
            icon='🔬',
            color='#5a9a8f',
            description='默认关键词组',
            keywords=old_keywords,
            match_mode='any',
            min_match_score=0.3
        )
        
        return result
    
    def _group_to_dict(self, group: KeywordGroup) -> Dict:
        """将KeywordGroup对象转换为字典"""
        return {
            'id': group.id,
            'user_id': group.user_id,
            'name': group.name,
            'icon': group.icon,
            'color': group.color,
            'description': group.description,
            'keywords': group.keywords,
            'match_mode': group.match_mode,
            'min_match_score': group.min_match_score,
            'is_active': group.is_active,
            'created_at': group.created_at.isoformat() if hasattr(group.created_at, 'isoformat') else group.created_at,
            'updated_at': group.updated_at.isoformat() if hasattr(group.updated_at, 'isoformat') else group.updated_at
        }
