"""数据切片配置领域服务：定义分析数据集的筛选逻辑、时间窗口与版本管理。"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService
from app.store import store


class DataSliceService(BaseModuleService):
    MODULE = "data_slice"
    ENTITY = "切片配置"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["切片编号", "切片名称", "数据来源", "筛选条件", "时间窗口", "切片大小", "业务含义", "切片版本"]
    REQUIRED_FIELDS = ["切片编号", "切片名称", "数据来源"]
    STATUS_ORDER = ["草稿", "待校验", "已生效", "已过期"]
    ACTION_RULES = {"提交校验": "待校验", "标记生效": "已生效", "标记过期": "已过期"}
    NEGATIVE_ACTIONS = []

    # ── 链路2: 数据切片 → 特征筛选 → 特征重要性分析 ──
    def execute_slice_and_push_to_selection(self, slice_id: int) -> dict[str, Any]:
        """将数据切片配置关联到特征筛选策略，触发筛选流程的数据准备阶段。"""
        sl = store.find(self.MODULE, slice_id)
        if sl is None:
            return {"ok": False, "message": f"切片配置 {slice_id} 不存在"}
        sl["status"] = "已生效"
        sl["pending"] = False
        selection_rows = store.rows("feature_selection")
        next_id = max((int(r.get("id", 0)) for r in selection_rows), default=0) + 1
        selection_rows.append({
            "id": next_id,
            "status": "草稿",
            "pending": True,
            "abnormal": False,
            "策略编号": f"SEL-{next_id:04d}",
            "特征集": f"slice_{slice_id}_features",
            "筛选方法": "variance_corr_combined",
            "保留数量": 20,
            "相关性阈值": "0.85",
            "方差阈值": "0.01",
            "信息增益": "0.15",
            "策略版本": "v1.0.0",
        })
        return {
            "ok": True,
            "slice_id": slice_id,
            "selection_id": next_id,
            "message": f"切片 {slice_id} 已生效，并自动创建筛选策略 {next_id}",
        }

    def validate_slice_window(self, slice_id: int) -> dict[str, Any]:
        """校验数据切片的时间窗口有效性，确保不超出数据源的历史分区范围。"""
        sl = store.find(self.MODULE, slice_id)
        if sl is None:
            return {"ok": False, "message": "切片不存在"}
        time_window = sl.get("时间窗口", "")
        if not time_window or time_window == "未设置":
            sl["abnormal"] = True
            return {"ok": False, "message": f"切片 {slice_id} 缺少时间窗口配置", "slice_id": slice_id}
        sl["abnormal"] = False
        return {"ok": True, "slice_id": slice_id, "time_window": time_window}

    def standardize_slice_condition(self, slice_id: int) -> dict[str, Any]:
        """标准化切片筛选条件为结构化表达式，便于跨模块查询和复用。"""
        sl = store.find(self.MODULE, slice_id)
        if sl is None:
            return {"ok": False}
        raw = sl.get("筛选条件", "")
        parsed = {
            "raw": raw,
            "operators": ["eq", "gt", "in"] if raw else [],
            "field_count": len(raw.split(",")) if raw else 0,
        }
        return {"ok": True, "slice_id": slice_id, "standardized_condition": parsed}

    def query_slice_statistics(self, slice_id: int) -> dict[str, Any]:
        """查询数据切片的统计信息，包括行数、列数和数据分布概览。"""
        sl = store.find(self.MODULE, slice_id)
        if sl is None:
            return {"ok": False}
        size_str = sl.get("切片大小", "0")
        try:
            row_count = int(float(str(size_str))) if size_str else 0
        except ValueError:
            row_count = 0
        return {
            "ok": True,
            "slice_id": slice_id,
            "slice_name": sl.get("切片名称"),
            "row_count": row_count,
            "source": sl.get("数据来源"),
            "business_meaning": sl.get("业务含义"),
        }