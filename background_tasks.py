"""
后台任务管理器
用于处理耗时操作，如缩略图生成和邮件发送
"""
import os
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty
from dataclasses import dataclass
from typing import Optional, Callable, Any, Dict
from datetime import datetime

# 设置日志
logger = logging.getLogger(__name__)


@dataclass
class Task:
    """任务数据结构"""
    id: str
    func: Callable
    args: tuple
    kwargs: Dict[str, Any]
    max_retries: int = 3
    current_retry: int = 0
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


class BackgroundTaskManager:
    """后台任务管理器"""
    
    def __init__(self, max_workers: int = 4, app=None):
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.task_queue = Queue()
        self.running_tasks = {}
        self.completed_tasks = {}
        self.failed_tasks = {}
        self._shutdown = False
        self._worker_thread = None
        self.app = app  # Store Flask app reference
        
        # 启动工作线程
        self.start()
        
    def start(self):
        """启动后台任务处理器"""
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._shutdown = False
            self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._worker_thread.start()
            logger.info(f"后台任务管理器启动，工作线程数: {self.max_workers}")
    
    def stop(self):
        """停止后台任务处理器"""
        self._shutdown = True
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)
        self.executor.shutdown(wait=True)
        logger.info("后台任务管理器已停止")
    
    def submit_task(self, task_id: str, func: Callable, *args, max_retries: int = 3, **kwargs) -> None:
        """提交任务到队列"""
        task = Task(
            id=task_id,
            func=func,
            args=args,
            kwargs=kwargs,
            max_retries=max_retries
        )
        self.task_queue.put(task)
        logger.info(f"任务已提交: {task_id}")
    
    def _execute_with_context(self, func, args, kwargs):
        """在Flask应用上下文中执行函数"""
        if self.app:
            with self.app.app_context():
                return func(*args, **kwargs)
        else:
            # 如果没有app引用，尝试获取当前app
            try:
                from flask import current_app
                with current_app.app_context():
                    return func(*args, **kwargs)
            except:
                # 没有应用上下文，直接执行
                return func(*args, **kwargs)
    
    def _worker_loop(self):
        """工作线程主循环"""
        while not self._shutdown:
            try:
                # 从队列获取任务，超时1秒
                task = self.task_queue.get(timeout=1)
                self._process_task(task)
            except Empty:
                continue
            except Exception as e:
                logger.error(f"工作线程异常: {e}")
    
    def _process_task(self, task: Task):
        """处理单个任务"""
        task_id = task.id
        self.running_tasks[task_id] = task
        
        try:
            logger.info(f"开始处理任务: {task_id} (尝试 {task.current_retry + 1}/{task.max_retries + 1})")
            
            # 使用线程池执行任务（带应用上下文）
            future = self.executor.submit(self._execute_with_context, task.func, task.args, task.kwargs)
            result = future.result(timeout=300)  # 5分钟超时
            
            # 任务成功
            self.completed_tasks[task_id] = {
                'task': task,
                'result': result,
                'completed_at': datetime.utcnow()
            }
            logger.info(f"任务完成: {task_id}")
            
        except Exception as e:
            logger.error(f"任务执行失败: {task_id}, 错误: {e}")
            
            # 重试机制
            if task.current_retry < task.max_retries:
                task.current_retry += 1
                # 延迟重试（指数退避）
                delay = 2 ** task.current_retry
                logger.info(f"任务 {task_id} 将在 {delay} 秒后重试")
                
                def retry_task():
                    time.sleep(delay)
                    if not self._shutdown:
                        self.task_queue.put(task)
                
                threading.Thread(target=retry_task, daemon=True).start()
            else:
                # 重试次数耗尽，标记为失败
                self.failed_tasks[task_id] = {
                    'task': task,
                    'error': str(e),
                    'failed_at': datetime.utcnow()
                }
                logger.error(f"任务最终失败: {task_id}")
        
        finally:
            # 从运行中任务列表移除
            self.running_tasks.pop(task_id, None)
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """获取任务状态"""
        if task_id in self.running_tasks:
            return {'status': 'running', 'task': self.running_tasks[task_id]}
        elif task_id in self.completed_tasks:
            return {'status': 'completed', **self.completed_tasks[task_id]}
        elif task_id in self.failed_tasks:
            return {'status': 'failed', **self.failed_tasks[task_id]}
        else:
            return {'status': 'not_found'}
    
    def get_stats(self) -> Dict[str, int]:
        """获取任务统计信息"""
        return {
            'queue_size': self.task_queue.qsize(),
            'running_count': len(self.running_tasks),
            'completed_count': len(self.completed_tasks),
            'failed_count': len(self.failed_tasks)
        }
    
    def cleanup_old_tasks(self, hours: int = 24):
        """清理旧任务记录"""
        cutoff_time = datetime.utcnow().timestamp() - (hours * 3600)
        
        # 清理已完成的任务
        to_remove = []
        for task_id, task_info in self.completed_tasks.items():
            if task_info['completed_at'].timestamp() < cutoff_time:
                to_remove.append(task_id)
        
        for task_id in to_remove:
            del self.completed_tasks[task_id]
        
        # 清理失败的任务
        to_remove = []
        for task_id, task_info in self.failed_tasks.items():
            if task_info['failed_at'].timestamp() < cutoff_time:
                to_remove.append(task_id)
        
        for task_id in to_remove:
            del self.failed_tasks[task_id]
        
        logger.info(f"清理了 {len(to_remove)} 个旧任务记录")


# 全局任务管理器实例
_task_manager: Optional[BackgroundTaskManager] = None


def get_task_manager(app=None) -> BackgroundTaskManager:
    """获取全局任务管理器实例"""
    global _task_manager
    if _task_manager is None:
        _task_manager = BackgroundTaskManager(app=app)
    elif app and not _task_manager.app:
        # 如果传入了app但管理器还没有app引用，更新它
        _task_manager.app = app
    return _task_manager


def shutdown_task_manager():
    """关闭全局任务管理器"""
    global _task_manager
    if _task_manager:
        _task_manager.stop()
        _task_manager = None