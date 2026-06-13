import jieba
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict
from .storage import MemoryStorage

NEGATIVE_KEYWORDS = {
    '退款', '退钱', '退货', '取消订单', '注销', '销户', '删除账号',
    '投诉', '举报', '不满', '太差', '垃圾', '不好', '失望', '骗人',
    '欺诈', '客服态度', '慢', '卡', 'bug', '崩溃', '打不开', '登录失败',
    '扣费', '乱收费', '涨价', '太贵', '不划算', '没用', '放弃',
    '卸载', '不用了', '再也不来', '差评', '一星', '怎么注销',
    '怎么退款', '如何退款', '为什么', '凭什么', '不合理'
}

SEARCH_EVENTS = {'search', 'query', 'search_keyword', 'search_submit'}
FEEDBACK_EVENTS = {'feedback', 'submit_feedback', 'comment', 'review', 'rating'}

class ChurnModule:
    def __init__(self):
        self.storage = MemoryStorage()
        jieba.initialize()

    def create_rule(self, name: str, conditions: List[Dict[str, Any]],
                    description: str = None) -> Dict[str, Any]:
        for idx, condition in enumerate(conditions):
            if 'type' not in condition:
                return {"success": False, "error": f"Condition {idx} missing 'type' field"}
            
            cond_type = condition['type']
            if cond_type == 'no_activity':
                if 'days' not in condition:
                    return {"success": False, "error": f"Condition {idx} (no_activity) missing 'days' field"}
                if not isinstance(condition['days'], int) or condition['days'] <= 0:
                    return {"success": False, "error": f"Condition {idx} 'days' must be a positive integer"}
            elif cond_type == 'no_purchase':
                if 'days' not in condition:
                    return {"success": False, "error": f"Condition {idx} (no_purchase) missing 'days' field"}
                if not isinstance(condition['days'], int) or condition['days'] <= 0:
                    return {"success": False, "error": f"Condition {idx} 'days' must be a positive integer"}
            elif cond_type == 'negative_behavior':
                pass
            elif cond_type == 'event_count':
                if 'event_name' not in condition or 'operator' not in condition or 'threshold' not in condition or 'days' not in condition:
                    return {"success": False, "error": f"Condition {idx} (event_count) missing required fields"}
            else:
                return {"success": False, "error": f"Unknown condition type: {cond_type}. Valid types: no_activity, no_purchase, negative_behavior, event_count"}

        rule = {
            "name": name,
            "conditions": conditions,
            "description": description,
            "last_run_time": None,
            "last_churn_count": 0
        }
        
        rule_id = self.storage.save_churn_rule(rule)
        
        return {
            "success": True,
            "rule_id": rule_id
        }

    def _check_condition(self, user_id: str, condition: Dict[str, Any], 
                         now: float) -> bool:
        cond_type = condition['type']
        user = self.storage.get_user(user_id)
        if not user:
            return False

        if cond_type == 'no_activity':
            days = condition['days']
            cutoff = now - days * 86400
            return user['last_active'] < cutoff

        elif cond_type == 'no_purchase':
            days = condition['days']
            cutoff = now - days * 86400
            filters = {
                "user_id": user_id,
                "event_name": lambda e: e in ['order_completed', 'payment_completed', 'purchase'],
                "timestamp": lambda t: t >= cutoff
            }
            events = self.storage.get_events(filters)
            return len(events) == 0

        elif cond_type == 'event_count':
            event_name = condition['event_name']
            operator = condition['operator']
            threshold = condition['threshold']
            days = condition.get('days', 30)
            
            cutoff = now - days * 86400
            filters = {
                "user_id": user_id,
                "event_name": event_name,
                "timestamp": lambda t: t >= cutoff
            }
            events = self.storage.get_events(filters)
            count = len(events)
            
            if operator == '>':
                return count > threshold
            elif operator == '>=':
                return count >= threshold
            elif operator == '<':
                return count < threshold
            elif operator == '<=':
                return count <= threshold
            elif operator in ['==', '=']:
                return count == threshold
            elif operator == '!=':
                return count != threshold
            return False

        elif cond_type == 'negative_behavior':
            cutoff = now - 30 * 86400
            filters = {
                "user_id": user_id,
                "event_name": lambda e: e in SEARCH_EVENTS or e in FEEDBACK_EVENTS,
                "timestamp": lambda t: t >= cutoff
            }
            events = self.storage.get_events(filters)
            negative_count = 0
            for event in events:
                props = event.get('properties', {})
                text = str(props.get('keyword', '') or props.get('content', '') or props.get('comment', ''))
                if text:
                    words = jieba.lcut(text.lower())
                    for word in words:
                        if word in NEGATIVE_KEYWORDS:
                            negative_count += 1
                            break
            return negative_count >= condition.get('min_count', 2)

        return False

    def _infer_churn_reason(self, user_id: str, now: float) -> List[Dict[str, Any]]:
        cutoff = now - 30 * 86400
        filters = {
            "user_id": user_id,
            "timestamp": lambda t: t >= cutoff
        }
        events = self.storage.get_events(filters)
        
        reasons = []
        negative_events = []
        refund_events = []
        complaint_events = []
        login_fail_events = []
        
        for event in events:
            props = event.get('properties', {})
            
            if event['event_name'] in SEARCH_EVENTS:
                keyword = str(props.get('keyword', '')).lower()
                if keyword:
                    words = jieba.lcut(keyword)
                    matched_keywords = [w for w in words if w in NEGATIVE_KEYWORDS]
                    if matched_keywords:
                        negative_events.append({
                            "time": event['timestamp'],
                            "datetime": datetime.fromtimestamp(event['timestamp']).isoformat(),
                            "type": "search",
                            "keyword": keyword,
                            "matched_keywords": matched_keywords,
                            "severity": "high" if any(k in keyword for k in ['注销', '退款', '投诉', '垃圾']) else "medium"
                        })
            
            if event['event_name'] in ['refund_request', 'refund_submit', 'order_cancelled']:
                refund_events.append({
                    "time": event['timestamp'],
                    "datetime": datetime.fromtimestamp(event['timestamp']).isoformat(),
                    "type": "refund",
                    "order_id": props.get('order_id'),
                    "amount": props.get('amount'),
                    "severity": "high"
                })
            
            if event['event_name'] in FEEDBACK_EVENTS:
                content = str(props.get('content', '') or props.get('comment', ''))
                rating = props.get('rating', 5)
                if rating and isinstance(rating, (int, float)) and rating <= 2:
                    complaint_events.append({
                        "time": event['timestamp'],
                        "datetime": datetime.fromtimestamp(event['timestamp']).isoformat(),
                        "type": "low_rating",
                        "rating": rating,
                        "content": content[:100] if content else None,
                        "severity": "high" if rating <= 1 else "medium"
                    })
                elif content:
                    words = jieba.lcut(content.lower())
                    matched_keywords = [w for w in words if w in NEGATIVE_KEYWORDS]
                    if matched_keywords:
                        complaint_events.append({
                            "time": event['timestamp'],
                            "datetime": datetime.fromtimestamp(event['timestamp']).isoformat(),
                            "type": "negative_feedback",
                            "content": content[:100],
                            "matched_keywords": matched_keywords,
                            "severity": "medium"
                        })
            
            if event['event_name'] in ['login_fail', 'login_error', 'auth_fail']:
                login_fail_events.append({
                    "time": event['timestamp'],
                    "datetime": datetime.fromtimestamp(event['timestamp']).isoformat(),
                    "type": "login_failure",
                    "reason": props.get('error_reason'),
                    "severity": "medium"
                })
        
        all_negative = negative_events + refund_events + complaint_events + login_fail_events
        
        if refund_events:
            reasons.append({
                "code": "REFUND_ACTIVITY",
                "severity": "high",
                "description": f"用户提交了 {len(refund_events)} 次退款申请，可能对产品或服务不满",
                "evidence": refund_events
            })
        
        if len(negative_events) >= 3:
            reasons.append({
                "code": "MULTIPLE_NEGATIVE_SEARCHES",
                "severity": "high",
                "description": f"用户在30天内搜索了 {len(negative_events)} 次负面关键词，如退款、注销等",
                "evidence": negative_events
            })
        elif len(negative_events) >= 1:
            reasons.append({
                "code": "NEGATIVE_SEARCH",
                "severity": "medium",
                "description": f"用户搜索过负面关键词，关注退款、注销等问题",
                "evidence": negative_events
            })
        
        if complaint_events:
            reasons.append({
                "code": "NEGATIVE_FEEDBACK",
                "severity": "high",
                "description": f"用户提交了 {len(complaint_events)} 次负面反馈或低评分",
                "evidence": complaint_events
            })
        
        if login_fail_events:
            reasons.append({
                "code": "LOGIN_ISSUES",
                "severity": "medium",
                "description": f"用户遇到 {len(login_fail_events)} 次登录失败，可能影响使用体验",
                "evidence": login_fail_events
            })
        
        user = self.storage.get_user(user_id)
        if user:
            days_since_active = (now - user['last_active']) / 86400
            if days_since_active >= 30:
                reasons.append({
                    "code": "LONG_TERM_INACTIVE",
                    "severity": "high",
                    "description": f"用户已 {int(days_since_active)} 天未活跃，属于长期沉默用户"
                })
            elif days_since_active >= 14:
                reasons.append({
                    "code": "INACTIVE",
                    "severity": "medium",
                    "description": f"用户已 {int(days_since_active)} 天未活跃"
                })
        
        if not reasons:
            reasons.append({
                "code": "PATTERN_BASED",
                "severity": "low",
                "description": "基于行为模式判断可能流失，无明确负面信号",
                "evidence": []
            })
        
        return sorted(reasons, key=lambda r: {"high": 0, "medium": 1, "low": 2}[r["severity"]])

    def run_churn_detection(self, rule_id: str, 
                            check_data_integrity: bool = True,
                            data_lag_threshold_hours: int = 2) -> Dict[str, Any]:
        rule = self.storage.get_churn_rule(rule_id)
        if not rule:
            return {"success": False, "error": f"Rule {rule_id} not found"}
        
        if not rule.get('enabled', True):
            return {"success": False, "error": "Rule is disabled"}
        
        if check_data_integrity:
            lag_hours = self.storage.get_data_lag_hours()
            if lag_hours > data_lag_threshold_hours:
                return {
                    "success": False,
                    "error": f"Data integrity check failed. Data lag is {lag_hours:.1f} hours, threshold is {data_lag_threshold_hours} hours. Skipping churn detection.",
                    "data_lag_hours": lag_hours,
                    "threshold_hours": data_lag_threshold_hours,
                    "skipped": True
                }
        
        now = datetime.now().timestamp()
        conditions = rule['conditions']
        
        churn_users = []
        all_user_ids = list(self.storage.user_profiles.keys())
        
        for user_id in all_user_ids:
            matches_all = True
            for condition in conditions:
                if not self._check_condition(user_id, condition, now):
                    matches_all = False
                    break
            
            if matches_all:
                reasons = self._infer_churn_reason(user_id, now)
                user = self.storage.get_user(user_id)
                
                churn_users.append({
                    "user_id": user_id,
                    "rule_id": rule_id,
                    "detected_at": now,
                    "last_active": user['last_active'] if user else None,
                    "last_active_days": round((now - user['last_active']) / 86400, 1) if user else None,
                    "user_level": user.get('user_level') if user else None,
                    "total_spent": user.get('total_spent', 0) if user else 0,
                    "order_count": user.get('order_count', 0) if user else 0,
                    "reasons": reasons,
                    "top_severity": reasons[0]['severity'] if reasons else "low",
                    "reached": False,
                    "recall_success": None
                })
        
        results = []
        for churn in churn_users:
            history = self.storage.get_reach_history(user_id=churn['user_id'], rule_id=rule_id)
            recent_reach = [h for h in history if now - h.get('reach_time', 0) < 7 * 86400]
            if recent_reach:
                churn['reached'] = True
                churn['last_reach_time'] = recent_reach[-1]['reach_time']
                churn['recall_success'] = self._check_recall(churn['user_id'], recent_reach[-1]['reach_time'], now)
            
            results.append(churn)
        
        self.storage.save_churn_results(results)
        
        rule['last_run_time'] = now
        rule['last_churn_count'] = len(results)
        self.storage.save_churn_rule(rule)
        
        severity_summary = defaultdict(int)
        for r in results:
            severity_summary[r['top_severity']] += 1
        
        return {
            "success": True,
            "rule_id": rule_id,
            "run_time": now,
            "total_users_checked": len(all_user_ids),
            "churn_users_found": len(results),
            "already_reached": sum(1 for r in results if r['reached']),
            "recall_success_count": sum(1 for r in results if r['recall_success']),
            "severity_distribution": dict(severity_summary),
            "results": results
        }

    def _check_recall(self, user_id: str, reach_time: float, now: float) -> bool:
        cutoff = reach_time + 7 * 86400
        if now < cutoff:
            return False
        
        filters = {
            "user_id": user_id,
            "timestamp": lambda t: t >= reach_time and t <= cutoff
        }
        events = self.storage.get_events(filters)
        
        important_events = ['login', 'page_view', 'add_to_cart', 'order_created', 'order_completed']
        for event in events:
            if event['event_name'] in important_events:
                return True
        
        return False

    def record_reach(self, rule_id: str, user_ids: List[str],
                     channel: str, content: str = None) -> Dict[str, Any]:
        now = datetime.now().timestamp()
        records = []
        
        for user_id in user_ids:
            history = self.storage.get_reach_history(user_id=user_id, rule_id=rule_id)
            recent_reach = [h for h in history if now - h.get('reach_time', 0) < 3 * 86400]
            
            if recent_reach:
                continue
            
            records.append({
                "user_id": user_id,
                "rule_id": rule_id,
                "channel": channel,
                "content": content,
                "reach_time": now,
                "recall_evaluated": False,
                "recall_success": None,
                "recall_evaluate_time": None
            })
        
        if records:
            self.storage.add_reach_history(records)
        
        return {
            "success": True,
            "attempted": len(user_ids),
            "recorded": len(records),
            "skipped_due_to_frequency": len(user_ids) - len(records)
        }

    def evaluate_recall(self, rule_id: str = None) -> Dict[str, Any]:
        now = datetime.now().timestamp()
        history = self.storage.get_reach_history(rule_id=rule_id)
        
        to_evaluate = [
            h for h in history 
            if not h.get('recall_evaluated') 
            and now - h.get('reach_time', 0) >= 7 * 86400
        ]
        
        updated = 0
        recalled = 0
        
        for record in to_evaluate:
            user_id = record['user_id']
            reach_time = record['reach_time']
            
            is_recalled = self._check_recall(user_id, reach_time, now)
            
            record['recall_evaluated'] = True
            record['recall_success'] = is_recalled
            record['recall_evaluate_time'] = now
            
            updated += 1
            if is_recalled:
                recalled += 1
        
        self.storage.save_snapshot('reach_history')
        
        return {
            "success": True,
            "evaluated": updated,
            "recalled": recalled,
            "recall_rate": round(recalled / updated, 4) if updated > 0 else None
        }

    def get_churn_results(self, rule_id: str = None, 
                          limit: int = 100) -> Dict[str, Any]:
        results = self.storage.get_churn_results(rule_id)
        
        return {
            "success": True,
            "total": len(results),
            "results": results[:limit]
        }

    def get_rules(self) -> Dict[str, Any]:
        rules = self.storage.get_all_churn_rules()
        return {
            "success": True,
            "rules": rules
        }

    def get_reach_history(self, rule_id: str = None, 
                          user_id: str = None) -> Dict[str, Any]:
        history = self.storage.get_reach_history(user_id=user_id, rule_id=rule_id)
        return {
            "success": True,
            "total": len(history),
            "history": history
        }

    def get_data_integrity_status(self) -> Dict[str, Any]:
        lag_hours = self.storage.get_data_lag_hours()
        is_complete = self.storage.is_data_complete(2)
        
        return {
            "success": True,
            "data_lag_hours": round(lag_hours, 2),
            "is_data_complete_for_churn": is_complete,
            "threshold_hours": 2,
            "last_event_timestamp": self.storage.last_event_timestamp,
            "last_event_datetime": datetime.fromtimestamp(self.storage.last_event_timestamp).isoformat() if self.storage.last_event_timestamp else None
        }
