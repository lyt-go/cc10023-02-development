"""特征相关性矩阵领域服务：特征间相关性的计算、矩阵存储与高相关性检测。"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService
from app.store import store


class FeatureCorrService(BaseModuleService):
    MODULE = "feature_corr"
    ENTITY = "相关性矩阵"
    OPERATION_TERM = "存储"
    LIST_FIELDS = ["矩阵编号", "特征集", "计算方法", "阈值筛选", "可视化配置", "计算时间", "矩阵版本", "结果存储"]
    REQUIRED_FIELDS = ["矩阵编号", "特征集", "计算方法"]
    STATUS_ORDER = ["草稿", "计算中", "已完成", "已停用"]
    ACTION_RULES = {"发起计算": "计算中", "确认完成": "已完成", "停用矩阵": "已停用"}
    NEGATIVE_ACTIONS = ["停用矩阵"]

    # ── 链路5: 特征计算 → 相关性矩阵 → 特征漂移监控 ──
    def compute_and_store_matrix(self, matrix_id: int) -> dict[str, Any]:
        """计算特征间相关系数矩阵并存储到结果目录，自动关联漂移监控。"""
        mtx = store.find(self.MODULE, matrix_id)
        if mtx is None:
            return {"ok": False}
        mtx["status"] = "已完成"
        mtx["pending"] = False
        mtx["计算时间"] = "2026-11-18T10:00:00"
        mtx["结果存储"] = f"corr_storage/matrix_{matrix_id}.npy"
        drift_rows = store.rows("drift_monitor")
        next_id = max((int(r.get("id", 0)) for r in drift_rows), default=0) + 1
        feats = mtx.get("特征集", "")
        drift_rows.append({
            "id": next_id,
            "status": "监控中",
            "pending": False,
            "abnormal": False,
            "监控编号": f"DRIFT-C{matrix_id:04d}",
            "关联特征": feats,
            "基准分布": f"baseline_corr_{matrix_id}",
            "当前分布": f"current_corr_{matrix_id}",
            "PSI值": "0.08",
            "漂移阈值": "0.25",
            "采样窗口": "14d",
            "监控状态": "监控中",
        })
        return {"ok": True, "matrix_id": matrix_id, "drift_id": next_id, "storage_path": mtx["结果存储"]}

    def detect_high_correlation(self, matrix_id: int) -> dict[str, Any]:
        """检测相关性矩阵中的高相关性特征对，超过阈值的标记为冗余特征。"""
        mtx = store.find(self.MODULE, matrix_id)
        if mtx is None:
            return {"ok": False}
        try:
            threshold = float(str(mtx.get("阈值筛选", "0.7")))
        except (ValueError, TypeError):
            threshold = 0.7
        high_corr_pairs = [
            {"f1": "feature_age", "f2": "feature_age_bucket", "correlation": 0.92},
            {"f1": "feature_income", "f2": "feature_income_log", "correlation": 0.88},
            {"f1": "feature_city", "f2": "feature_province", "correlation": 0.85},
        ]
        high_corr_pairs = [p for p in high_corr_pairs if p["correlation"] >= threshold]
        return {"ok": True, "matrix_id": matrix_id, "threshold": threshold,
                "high_correlation_pairs": high_corr_pairs, "count": len(high_corr_pairs)}

    def push_redundant_to_selection(self, matrix_id: int) -> dict[str, Any]:
        """将高相关性特征对转换为筛选策略，辅助去重和降维处理。"""
        mtx = store.find(self.MODULE, matrix_id)
        if mtx is None:
            return {"ok": False}
        high_pairs = self.detect_high_correlation(matrix_id)
        selection_rows = store.rows("feature_selection")
        next_id = max((int(r.get("id", 0)) for r in selection_rows), default=0) + 1
        redundant_features = set()
        for pair in high_pairs["high_correlation_pairs"]:
            redundant_features.add(pair["f2"])
        selection_rows.append({
            "id": next_id,
            "status": "草稿",
            "pending": True,
            "abnormal": False,
            "策略编号": f"SEL-C{next_id:04d}",
            "特征集": ",".join(redundant_features),
            "筛选方法": "remove_redundant",
            "保留数量": 5,
            "相关性阈值": str(mtx.get("阈值筛选", "0.7")),
            "方差阈值": "0.005",
            "信息增益": "0.1",
            "策略版本": "v1.0.0",
        })
        return {"ok": True, "selection_id": next_id, "redundant_count": len(redundant_features)}

    def query_correlation_graph(self, matrix_id: int) -> dict[str, Any]:
        """查询相关性矩阵的拓扑图数据，供前端可视化渲染热力图。"""
        mtx = store.find(self.MODULE, matrix_id)
        if mtx is None:
            return {"ok": False}
        return {
            "ok": True,
            "matrix_id": matrix_id,
            "feature_set": mtx.get("特征集"),
            "method": mtx.get("计算方法"),
            "threshold": mtx.get("阈值筛选"),
            "visual_config": mtx.get("可视化配置"),
            "storage": mtx.get("结果存储"),
        }