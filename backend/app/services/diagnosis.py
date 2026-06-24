"""
DiagnosisService - 能力诊断服务

将"错题标签"升级为"能力诊断"：
- 定位薄弱知识点
- 判断错误类型（7大类）
- 生成诊断结论
- 计算掌握度变化量
- 生成复习建议

错误类型分类：
    concept_missing       没学会核心概念
    concept_confusion     两个概念混淆
    reasoning_gap         推理链断裂
    application_error     会背不会用
    coding_error          代码实现错误
    expression_problem    表达不完整
    careless_error        粗心或漏答
"""
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ============== 错误类型定义 ==============

ERROR_CATEGORIES = {
    "concept_missing": {
        "label": "概念缺失",
        "description": "未掌握核心概念，答案缺乏关键知识点",
        "mastery_penalty": 25.0,
        "review_priority": 9,
    },
    "concept_confusion": {
        "label": "概念混淆",
        "description": "将两个相似概念混为一谈",
        "mastery_penalty": 20.0,
        "review_priority": 8,
    },
    "reasoning_gap": {
        "label": "推理断裂",
        "description": "知道概念但推理链条不完整",
        "mastery_penalty": 15.0,
        "review_priority": 7,
    },
    "application_error": {
        "label": "应用错误",
        "description": "会背概念但不会应用到具体问题",
        "mastery_penalty": 18.0,
        "review_priority": 7,
    },
    "coding_error": {
        "label": "代码错误",
        "description": "代码实现存在语法或逻辑错误",
        "mastery_penalty": 15.0,
        "review_priority": 6,
    },
    "expression_problem": {
        "label": "表达不完整",
        "description": "理解了但表达有遗漏或不清晰",
        "mastery_penalty": 10.0,
        "review_priority": 5,
    },
    "careless_error": {
        "label": "粗心错误",
        "description": "实际掌握但因粗心答错",
        "mastery_penalty": 5.0,
        "review_priority": 3,
    },
}


# ============== DiagnosisService ==============

class DiagnosisService:
    """能力诊断服务

    输入：题目、用户答案、评判结果、题目关联的知识点
    输出：结构化诊断（错误类型、薄弱知识点、掌握度变化、复习建议）
    """

    def __init__(self):
        pass

    # ---------- 公开接口 ----------

    def diagnose(
        self,
        question: dict,
        evaluation: dict,
        knowledge_points: List[dict] = None,
        common_mistakes: List[dict] = None,
    ) -> dict:
        """
        对一道题的作答进行完整诊断。

        Args:
            question: 题目信息 {id, content, type, tags, sections, ...}
            evaluation: 评判结果 {correct, score, error_type, explanation, error_tags}
            knowledge_points: 题目关联的知识点 [{id, name, path, importance}]
            common_mistakes: 题目预置常见错误 [{error_type, description, kp_ids}]

        Returns:
            诊断结果 dict:
            {
                "error_category": str | None,
                "error_conclusion": str,
                "knowledge_point_ids": [str],
                "mastery_delta": {kp_id: float},
                "review_suggestions": [
                    {"action": str, "kp_id": str, "description": str, "priority": int}
                ],
            }
        """
        is_correct = evaluation.get("correct", False)
        score = evaluation.get("score", 0)

        # 答对了：只有正向掌握度提升，无错误诊断
        if is_correct:
            return self._diagnose_correct(question, evaluation, knowledge_points)

        # 答错了：进行完整错误诊断
        return self._diagnose_wrong(
            question, evaluation, knowledge_points, common_mistakes
        )

    # ---------- 答对处理 ----------

    def _diagnose_correct(
        self,
        question: dict,
        evaluation: dict,
        knowledge_points: List[dict] = None,
    ) -> dict:
        """答对的诊断：计算正向掌握度提升"""
        score = evaluation.get("score", 80)
        kps = knowledge_points or []

        # 根据得分计算掌握度增量
        # 95-100: +12, 80-94: +8, 60-79: +4
        if score >= 95:
            base_delta = 12.0
        elif score >= 80:
            base_delta = 8.0
        elif score >= 60:
            base_delta = 4.0
        else:
            base_delta = 2.0

        mastery_delta = {}
        kp_ids = []
        for kp in kps:
            kp_id = kp.get("id") or kp.get("kp_id")
            if not kp_id:
                continue
            kp_ids.append(kp_id)
            weight = kp.get("weight", 1.0)
            role = kp.get("role", "primary")
            # 主要知识点加得多，次要知识点加得少
            multiplier = 1.0 if role == "primary" else 0.5
            mastery_delta[str(kp_id)] = round(base_delta * weight * multiplier, 1)

        # 简单题加成更少（避免刷简单题刷分）
        difficulty = question.get("difficulty", "medium")
        diff_multiplier = {"easy": 0.7, "medium": 1.0, "hard": 1.3}.get(difficulty, 1.0)
        for kp_id in mastery_delta:
            mastery_delta[kp_id] = round(mastery_delta[kp_id] * diff_multiplier, 1)

        return {
            "error_category": None,
            "error_conclusion": "回答正确，知识点掌握良好",
            "knowledge_point_ids": kp_ids,
            "mastery_delta": mastery_delta,
            "review_suggestions": [],
        }

    # ---------- 答错处理 ----------

    def _diagnose_wrong(
        self,
        question: dict,
        evaluation: dict,
        knowledge_points: List[dict] = None,
        common_mistakes: List[dict] = None,
    ) -> dict:
        """答错的完整诊断流程"""
        kps = knowledge_points or []
        q_type = question.get("type", "text")
        score = evaluation.get("score", 0)
        error_type_raw = evaluation.get("error_type") or ""
        explanation = evaluation.get("explanation", "")

        # Step 1: 识别错误类别
        error_category = self._classify_error_category(
            q_type=q_type,
            score=score,
            error_type_raw=error_type_raw,
            explanation=explanation,
            common_mistakes=common_mistakes,
            user_answer=evaluation.get("user_answer", ""),
        )

        # Step 2: 定位薄弱知识点
        weak_kp_ids = self._identify_weak_kps(kps, error_category)
        all_kp_ids = [str(kp.get("id") or kp.get("kp_id")) for kp in kps if kp.get("id") or kp.get("kp_id")]

        # Step 3: 计算掌握度变化量
        mastery_delta = self._calculate_mastery_delta(kps, error_category, score)

        # Step 4: 生成诊断结论
        error_conclusion = self._generate_conclusion(
            error_category=error_category,
            kps=kps,
            weak_kp_ids=weak_kp_ids,
            explanation=explanation,
        )

        # Step 5: 生成复习建议
        review_suggestions = self._generate_review_suggestions(
            error_category=error_category,
            kps=kps,
            weak_kp_ids=weak_kp_ids,
            question=question,
        )

        return {
            "error_category": error_category,
            "error_conclusion": error_conclusion,
            "knowledge_point_ids": all_kp_ids,
            "weak_kp_ids": weak_kp_ids,
            "mastery_delta": mastery_delta,
            "review_suggestions": review_suggestions,
        }

    # ---------- Step 1: 错误分类 ----------

    def _classify_error_category(
        self,
        q_type: str,
        score: float,
        error_type_raw: str,
        explanation: str,
        common_mistakes: List[dict] = None,
        user_answer: str = "",
    ) -> str:
        """
        判断错误类型。

        优先级：
        1. 题目预置的 common_mistakes 匹配
        2. LLM 返回的 error_type 映射
        3. 基于得分和题型的启发式规则
        """
        error_type_raw = (error_type_raw or "").strip()

        # 规则1: 未作答 / 空白 → careless_error
        if not user_answer or not user_answer.strip():
            return "careless_error"

        # 规则2: 代码题 → coding_error（除非明确是其他类型）
        if q_type == "code" and "语法" in error_type_raw:
            return "coding_error"

        # 规则3: 常见错误映射匹配
        if common_mistakes:
            for mistake in common_mistakes:
                m_desc = (mistake.get("description") or "").lower()
                m_type = mistake.get("error_type", "")
                # 检查用户答案是否包含常见错误关键词
                if m_desc and m_desc in (explanation or "").lower():
                    if m_type in ERROR_CATEGORIES:
                        return m_type

        # 规则4: 基于 LLM error_type 的关键词映射
        error_keywords = {
            "concept_confusion": ["混淆", "混为一谈", "搞混", "搞反了", "张冠李戴"],
            "concept_missing": ["没学会", "不理解", "不知道", "完全错误", "不了解", "缺少", "缺乏"],
            "reasoning_gap": ["推理", "逻辑不完整", "推导", "链条", "思路"],
            "application_error": ["应用", "不会用", "生搬硬套", "适用场景"],
            "expression_problem": ["表达", "不完整", "遗漏", "说不清楚", "描述不清"],
            "careless_error": ["粗心", "漏看", "看错", "笔误", "不小心"],
            "coding_error": ["语法", "编译错误", "运行时错误", "bug"],
        }

        text_to_check = (error_type_raw + " " + explanation).lower()
        for category, keywords in error_keywords.items():
            for kw in keywords:
                if kw in text_to_check:
                    return category

        # 规则5: 基于得分的启发式
        if score == 0:
            return "concept_missing"
        elif score < 30:
            return "concept_missing"
        elif score < 50:
            return "concept_confusion"
        elif score < 70:
            return "reasoning_gap"
        else:
            return "expression_problem"

    # ---------- Step 2: 薄弱知识点定位 ----------

    def _identify_weak_kps(
        self,
        knowledge_points: List[dict],
        error_category: str,
    ) -> List[str]:
        """从题目关联的知识点中识别薄弱点"""
        kp_ids = []
        for kp in knowledge_points:
            kp_id = kp.get("id") or kp.get("kp_id")
            if not kp_id:
                continue
            role = kp.get("role", "primary")
            # 主要考察的知识点肯定是薄弱点
            if role == "primary":
                kp_ids.append(str(kp_id))
            # 概念混淆时，次要/干扰知识点也是薄弱点
            elif role in ("secondary", "distractor") and error_category == "concept_confusion":
                kp_ids.append(str(kp_id))

        return kp_ids

    # ---------- Step 3: 掌握度变化计算 ----------

    def _calculate_mastery_delta(
        self,
        knowledge_points: List[dict],
        error_category: str,
        score: float,
    ) -> Dict[str, float]:
        """
        计算每个知识点的掌握度变化量。

        答错惩罚公式：
            base_penalty = ERROR_CATEGORIES[error_category].mastery_penalty
            难度系数：hard × 1.2, medium × 1.0, easy × 0.8
            得分系数：0 分 × 1.0, 30 分 × 0.7, 50 分 × 0.5
        """
        category_info = ERROR_CATEGORIES.get(error_category, ERROR_CATEGORIES["concept_missing"])
        base_penalty = category_info["mastery_penalty"]

        # 得分越高，惩罚越小（说明部分掌握）
        score_factor = max(0.3, 1.0 - (score / 100.0) * 0.7)

        mastery_delta = {}
        for kp in knowledge_points:
            kp_id = kp.get("id") or kp.get("kp_id")
            if not kp_id:
                continue
            role = kp.get("role", "primary")
            weight = kp.get("weight", 1.0)

            # 主要知识点惩罚多，次要少
            role_multiplier = 1.0 if role == "primary" else 0.5
            if role == "distractor":
                role_multiplier = 0.3

            delta = round(-base_penalty * score_factor * weight * role_multiplier, 1)
            mastery_delta[str(kp_id)] = delta

        return mastery_delta

    # ---------- Step 4: 诊断结论生成 ----------

    def _generate_conclusion(
        self,
        error_category: str,
        kps: List[dict],
        weak_kp_ids: List[str],
        explanation: str,
    ) -> str:
        """生成通俗易懂的诊断结论"""
        category_info = ERROR_CATEGORIES.get(error_category, {})
        category_label = category_info.get("label", error_category)

        # 获取薄弱知识点名称
        weak_kp_names = []
        for kp in kps:
            kp_id = str(kp.get("id") or kp.get("kp_id", ""))
            if kp_id in weak_kp_ids:
                name = kp.get("name") or kp.get("kp_name", "")
                if name:
                    weak_kp_names.append(name)

        if weak_kp_names:
            kp_str = "、".join(weak_kp_names[:3])
            if error_category == "concept_confusion":
                return f"概念混淆：将 {kp_str} 相关概念与其他知识点混淆了"
            elif error_category == "concept_missing":
                return f"概念缺失：{kp_str} 的核心概念未掌握"
            elif error_category == "reasoning_gap":
                return f"推理断裂：{kp_str} 的推理链条不完整"
            elif error_category == "application_error":
                return f"应用错误：{kp_str} 的概念无法灵活应用"
            elif error_category == "coding_error":
                return f"代码错误：{kp_str} 相关代码实现有误"
            elif error_category == "expression_problem":
                return f"表达不完整：{kp_str} 理解了但描述有遗漏"
            elif error_category == "careless_error":
                return f"粗心失误：本应掌握 {kp_str}，但答题时粗心了"

        # 没有知识点信息时的通用结论
        if explanation:
            return f"{category_label}：{explanation[:80]}"
        return f"错误类型：{category_label}"

    # ---------- Step 5: 复习建议生成 ----------

    def _generate_review_suggestions(
        self,
        error_category: str,
        kps: List[dict],
        weak_kp_ids: List[str],
        question: dict,
    ) -> List[dict]:
        """
        生成具体的复习建议动作。

        动作类型：
        - review_material: 回看资料章节
        - practice_question: 做练习题目
        - concept_comparison: 概念对比辨析
        - follow_up_test: 后续复测
        """
        suggestions = []
        category_info = ERROR_CATEGORIES.get(error_category, {})
        base_priority = category_info.get("review_priority", 5)

        # 获取薄弱知识点详情
        weak_kps = []
        for kp in kps:
            kp_id = str(kp.get("id") or kp.get("kp_id", ""))
            if kp_id in weak_kp_ids:
                weak_kps.append(kp)

        if not weak_kps:
            # 没有知识点信息，给通用建议
            suggestions.append({
                "action": "review_material",
                "kp_id": None,
                "title": "回顾对应章节",
                "description": "回到学习材料中重新阅读相关内容",
                "priority": base_priority,
            })
            return suggestions

        # 针对每个薄弱知识点生成建议
        for i, kp in enumerate(weak_kps):
            kp_id = str(kp.get("id") or kp.get("kp_id"))
            kp_name = kp.get("name") or kp.get("kp_name", "相关知识点")

            # 建议1: 回看资料（所有错误类型都需要）
            suggestions.append({
                "action": "review_material",
                "kp_id": kp_id,
                "kp_name": kp_name,
                "title": f"回看「{kp_name}」章节",
                "description": f"重新学习 {kp_name} 的核心概念和关键细节",
                "priority": base_priority,
            })

            # 概念混淆 → 增加概念对比练习
            if error_category == "concept_confusion":
                suggestions.append({
                    "action": "concept_comparison",
                    "kp_id": kp_id,
                    "kp_name": kp_name,
                    "title": f"「{kp_name}」概念辨析",
                    "description": "对比易混淆概念的关键区别，做辨析题巩固",
                    "priority": base_priority - 1,
                })

            # 应用错误 → 增加应用题
            if error_category == "application_error":
                suggestions.append({
                    "action": "practice_question",
                    "kp_id": kp_id,
                    "kp_name": kp_name,
                    "title": f"「{kp_name}」应用题练习",
                    "description": "做 2-3 道应用题，训练概念的灵活运用",
                    "priority": base_priority - 1,
                })

            # 代码错误 → 增加代码练习
            if error_category == "coding_error":
                suggestions.append({
                    "action": "practice_question",
                    "kp_id": kp_id,
                    "kp_name": kp_name,
                    "title": f"「{kp_name}」代码练习",
                    "description": "重新手写代码并运行测试用例",
                    "priority": base_priority - 1,
                })

            # 限制每个知识点的建议数量
            if i >= 2:
                break

        # 最后加一条复测建议（间隔复习）
        if weak_kps:
            first_kp = weak_kps[0]
            kp_id = str(first_kp.get("id") or first_kp.get("kp_id"))
            suggestions.append({
                "action": "follow_up_test",
                "kp_id": kp_id,
                "kp_name": first_kp.get("name") or first_kp.get("kp_name", ""),
                "title": "48 小时后复测",
                "description": "间隔 48 小时后做 1-2 道题检验巩固效果",
                "priority": max(2, base_priority - 3),
                "delay_hours": 48,
            })

        return suggestions


# ============== 全局单例 ==============

_diagnosis_service = None


def get_diagnosis_service() -> DiagnosisService:
    global _diagnosis_service
    if _diagnosis_service is None:
        _diagnosis_service = DiagnosisService()
    return _diagnosis_service
