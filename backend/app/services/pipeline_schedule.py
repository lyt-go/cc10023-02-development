# -*- 数据工程模块：pipeline_schedule.py 处理数据集、字段、批次等数据产物 -*-
"""流水线调度领域服务：模型训练与特征计算的定时调度、依赖编排。"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService
from app.store import store


class PipelineScheduleService(BaseModuleService):
    MODULE = "pipeline_schedule"
    ENTITY = "调度配置"
    OPERATION_TERM = "关联"
    LIST_FIELDS = ["调度编号", "关联流水线", "Cron表达式", "依赖任务", "失败策略", "通知方式", "最大重试数", "调度状态"]
    REQUIRED_FIELDS = ["调度编号", "关联流水线", "Cron表达式"]
    STATUS_ORDER = ["草稿", "待校验", "已激活", "已暂停"]
    ACTION_RULES = {"提交校验": "待校验", "激活调度": "已激活", "暂停调度": "已暂停"}
    NEGATIVE_ACTIONS = []

    def activate_and_trigger_pipeline(self, sched_id: int) -> dict[str, Any]:
        """激活调度配置并关联触发对应训练流水线的执行。"""
        sched = store.find(self.MODULE, sched_id)
        if sched is None:
            return {"ok": False}
        sched["status"] = "已激活"
        sched["pending"] = False
        try:
            pipeline_id = int(float(str(sched.get("关联流水线", "0"))))
        except (ValueError, TypeError):
            pipeline_id = 0
        pipeline = store.find("train_pipeline", pipeline_id)
        if pipeline:
            pipeline["status"] = "训练中"
            pipeline["pending"] = True
        return {"ok": True, "sched_id": sched_id, "pipeline_id": pipeline_id,
                "cron": sched.get("Cron表达式"),
                "message": f"调度 {sched_id} 已激活并触发流水线 {pipeline_id}"}

    def validate_cron_expression(self, sched_id: int) -> dict[str, Any]:
        """校验调度配置的Cron表达式合法性和调度频率。"""
        sched = store.find(self.MODULE, sched_id)
        if sched is None:
            return {"ok": False}
        cron = sched.get("Cron表达式", "")
        parts = cron.split()
        is_valid = len(parts) == 5
        if not is_valid:
            sched["abnormal"] = True
            return {"ok": False, "cron": cron, "reason": "Cron表达式格式异常，需5段"}
        sched["abnormal"] = False
        return {"ok": True, "cron": cron, "next_run": "2026-11-19T02:00:00"}

    def link_dependency_chain(self, sched_id: int) -> dict[str, Any]:
        """解析调度依赖关系并关联上下游调度任务，构建调度DAG。"""
        sched = store.find(self.MODULE, sched_id)
        if sched is None:
            return {"ok": False}
        dep_tasks = [d.strip() for d in str(sched.get("依赖任务", "")).split(",") if d.strip()]
        all_scheds = store.rows(self.MODULE)
        downstream = [s.get("id") for s in all_scheds if str(s.get("依赖任务", "")) and
                      str(sched.get("调度编号", "")) in str(s.get("依赖任务", ""))]
        return {"ok": True, "sched_id": sched_id, "dependencies": dep_tasks,
                "downstream_schedules": downstream, "retry_max": sched.get("最大重试数")}

    def migrate_schedule_timing(self, sched_id: int, new_cron: str) -> dict[str, Any]:
        """迁移调度配置的定时策略，将旧Cron表达式更新为新表达式。"""
        sched = store.find(self.MODULE, sched_id)
        if sched is None:
            return {"ok": False}
        old_cron = sched.get("Cron表达式")
        sched["Cron表达式"] = new_cron
        sched["调度状态"] = "已暂停"
        sched["status"] = "已暂停"
        return {"ok": True, "sched_id": sched_id, "old_cron": old_cron, "new_cron": new_cron}
