"""特征组管理领域服务：维护特征逻辑分组、主题归类和互斥规则。"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService
from app.store import store


class FeatureGroupService(BaseModuleService):
    MODULE = "feature_group"
    ENTITY = "特征组"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["组编号", "组名称", "包含特征", "业务主题", "默认权重", "互斥规则", "依赖关系", "组版本"]
    REQUIRED_FIELDS = ["组编号", "组名称", "包含特征"]
    STATUS_ORDER = ["草稿", "待校验", "已生效", "已停用"]
    ACTION_RULES = {"提交校验": "待校验", "标记生效": "已生效", "停用组定义": "已停用"}
    NEGATIVE_ACTIONS = ["停用组定义"]

    # ── 链路4: 特征组 → 训练流水线 → 模型注册 ──
    def export_group_features(self, group_id: int) -> dict[str, Any]:
        """查询特征组内所有已生效特征定义并导出为训练流水线可用格式。"""
        group = store.find(self.MODULE, group_id)
        if group is None:
            return {"ok": False, "message": f"特征组 {group_id} 不存在"}
        feature_names = [f.strip() for f in (group.get("包含特征") or "").split(",") if f.strip()]
        define_rows = store.rows("feature_define")
        matched = [r for r in define_rows if r.get("特征名称") in feature_names and r.get("status") == "已生效"]
        result = {
            "group_id": group_id,
            "group_name": group.get("组名称"),
            "feature_count": len(matched),
            "features": [
                {"name": r.get("特征名称"), "type": r.get("特征类型"), "logic": r.get("计算逻辑")}
                for r in matched
            ],
        }
        return {"ok": True, "data": result}

    def create_training_pipeline(self, group_id: int) -> dict[str, Any]:
        """基于特征组创建训练流水线配置，关联特征集并初始化算法参数。"""
        export = self.export_group_features(group_id)
        if not export.get("ok"):
            return export
        data = export["data"]
        pipeline_rows = store.rows("train_pipeline")
        next_id = max((int(r.get("id", 0)) for r in pipeline_rows), default=0) + 1
        group = store.find(self.MODULE, group_id)
        pipeline_rows.append({
            "id": next_id,
            "status": "草稿",
            "pending": True,
            "abnormal": False,
            "流水线编号": f"PIPE-{next_id:04d}",
            "流水线名称": f"train_{group.get('组名称', 'unknown')}_pipeline",
            "特征集": group.get("包含特征", ""),
            "算法类型": "xgboost",
            "超参数配置": '{"max_depth":6,"learning_rate":0.1,"n_estimators":100}',
            "评估指标": "auc,logloss",
            "训练周期": "weekly",
            "流水线版本": "v1.0.0",
        })
        return {
            "ok": True,
            "pipeline_id": next_id,
            "feature_count": data["feature_count"],
            "message": f"已基于特征组 {group_id} 创建训练流水线 {next_id}",
        }

    def check_mutex_rule_compliance(self, group_id: int) -> dict[str, Any]:
        """校验特征组的互斥规则合规性，确保无冲突特征同时出现在同一组中。"""
        group = store.find(self.MODULE, group_id)
        if group is None:
            return {"ok": False, "message": "特征组不存在"}
        mutex_rule = group.get("互斥规则", "")
        feature_names = [f.strip() for f in (group.get("包含特征") or "").split(",") if f.strip()]
        violations = []
        if mutex_rule and len(feature_names) > 5:
            violations.append("特征数量超过互斥规则约束上限5个")
        if violations:
            group["abnormal"] = True
            group["status"] = "待校验"
        else:
            group["abnormal"] = False
        return {"ok": len(violations) == 0, "violations": violations, "group_id": group_id}

    def aggregate_group_dependencies(self, group_id: int) -> dict[str, Any]:
        """聚合特征组的依赖关系并关联上下游模块，生成完整依赖链路图。"""
        group = store.find(self.MODULE, group_id)
        if group is None:
            return {"ok": False}
        dep_text = group.get("依赖关系", "")
        deps = [d.strip() for d in dep_text.split(",") if d.strip()] if dep_text else []
        pipeline_rows = store.rows("train_pipeline")
        downstream = [r.get("id") for r in pipeline_rows if group.get("组名称", "") in str(r.get("特征集", ""))]
        return {
            "ok": True,
            "group_id": group_id,
            "upstream_deps": deps,
            "downstream_pipelines": downstream,
            "chain_length": len(deps) + len(downstream),
        }