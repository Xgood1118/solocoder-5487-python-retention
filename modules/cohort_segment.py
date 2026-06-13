import re
import ast
import operator
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Callable
from collections import defaultdict
from .storage import MemoryStorage
from .cohort import CohortModule

NEGATIVE_KEYWORDS = {'退款', '注销', '取消', '投诉', '不满', '太差', '垃圾', '不好'}
POSITIVE_KEYWORDS = {'好评', '推荐', '满意', '喜欢', '棒', '赞', '优秀'}

class SegmentExpressionParser:
    _OPERATORS = {
        'AND': all,
        'OR': any,
        'and': all,
        'or': any,
    }
    
    _COMPARISONS = {
        '>': operator.gt,
        '<': operator.lt,
        '>=': operator.ge,
        '<=': operator.le,
        '==': operator.eq,
        '!=': operator.ne,
        '=': operator.eq,
        'contains': lambda a, b: b in str(a).lower() if a else False,
        'in': lambda a, b: a in b,
        'not in': lambda a, b: a not in b,
    }

    def __init__(self):
        self.storage = MemoryStorage()

    def _tokenize(self, expression: str) -> List[str]:
        tokens = []
        i = 0
        while i < len(expression):
            if expression[i] in '()':
                tokens.append(expression[i])
                i += 1
            elif expression[i].isspace():
                i += 1
            elif expression[i] in '"\'':
                quote = expression[i]
                j = i + 1
                while j < len(expression) and expression[j] != quote:
                    j += 1
                tokens.append(expression[i:j+1])
                i = j + 1
            else:
                j = i
                while j < len(expression) and not expression[j].isspace() and expression[j] not in '()':
                    j += 1
                tokens.append(expression[i:j])
                i = j
        return tokens

    def validate_expression(self, expression: str) -> Dict[str, Any]:
        try:
            tokens = self._tokenize(expression)
            
            valid_conditions = [
                'event_count',
                'past',
                'days',
                'in',
                'device_type',
                'product_line',
                'event_name',
                'completed',
                'at_least',
                'more_than',
                'less_than',
                'times',
                'AND',
                'OR',
                'and',
                'or',
                '>',
                '<',
                '>=',
                '<=',
                '==',
                '!=',
                '=',
                'contains',
                'not',
            ]
            
            pattern = r"past\s+\d+\s+days(\s+in\s+['\"]\w+['\"])?\s+(event_count|completed|has)\s+['\"]\w+['\"]\s*([><=!]+\s*\d+|(at_least|more_than|less_than)\s+\d+\s+times?|at_least\s+\d+\s+['\"]\w+['\"])"
            full_pattern = r"^\s*(" + pattern + r")(\s+(AND|OR)\s+" + pattern + r")*\s*$"
            
            import re
            if not re.match(full_pattern, expression, re.IGNORECASE):
                return {
                    "valid": False,
                    "error": "Expression syntax invalid. Does not match expected pattern.",
                    "suggestion": "Example: past 30 days in 'ios' event_count 'page_view' > 3 AND past 30 days in 'web' event_count 'order_completed' >= 1"
                }
            
            return {"valid": True}
            
        except Exception as e:
            return {
                "valid": False,
                "error": f"Expression syntax error: {str(e)}",
                "suggestion": "Check expression syntax. Example: past 30 days in 'ios' event_count 'page_view' > 3 AND past 30 days in 'web' event_count 'order_completed' >= 1"
            }

    def parse_expression(self, expression: str) -> Optional[Callable[[str], bool]]:
        validation = self.validate_expression(expression)
        if not validation["valid"]:
            return None
        
        try:
            def evaluate(user_id: str) -> bool:
                return self._evaluate_expression(expression, user_id)
            return evaluate
        except Exception:
            return None

    def _evaluate_expression(self, expression: str, user_id: str) -> bool:
        now = datetime.now().timestamp()
        
        pattern = r"(past\s+(\d+)\s+days\s+(?:in\s+['\"](\w+)['\"]\s+)?event_count\s+['\"](\w+)['\"]\s*([><=!]+)\s*(\d+))"
        
        def replace_condition(match):
            full = match.group(1)
            days = int(match.group(2))
            device = match.group(3)
            event_name = match.group(4)
            op = match.group(5)
            threshold = int(match.group(6))
            
            start_time = now - days * 86400
            filters = {
                "user_id": user_id,
                "event_name": event_name,
                "timestamp": lambda t: t >= start_time
            }
            if device:
                filters["device_type"] = device
            
            events = self.storage.get_events(filters)
            count = len(events)
            
            if op == '>':
                result = count > threshold
            elif op == '<':
                result = count < threshold
            elif op == '>=':
                result = count >= threshold
            elif op == '<=':
                result = count <= threshold
            elif op in ['==', '=']:
                result = count == threshold
            elif op == '!=':
                result = count != threshold
            else:
                result = False
            
            return 'True' if result else 'False'
        
        pattern2 = r"(past\s+(\d+)\s+days\s+(?:in\s+['\"](\w+)['\"]\s+)?(?:completed|has)\s+['\"](\w+)['\"]\s+(at_least|more_than|less_than)\s+(\d+)\s+times)"
        
        def replace_condition2(match):
            full = match.group(1)
            days = int(match.group(2))
            device = match.group(3)
            event_name = match.group(4)
            qualifier = match.group(5)
            threshold = int(match.group(6))
            
            start_time = now - days * 86400
            filters = {
                "user_id": user_id,
                "event_name": event_name,
                "timestamp": lambda t: t >= start_time
            }
            if device:
                filters["device_type"] = device
            
            events = self.storage.get_events(filters)
            count = len(events)
            
            if qualifier == 'at_least':
                result = count >= threshold
            elif qualifier == 'more_than':
                result = count > threshold
            elif qualifier == 'less_than':
                result = count < threshold
            else:
                result = False
            
            return 'True' if result else 'False'
        
        pattern3 = r"(past\s+(\d+)\s+days\s+(?:in\s+['\"](\w+)['\"]\s+)?(?:completed|has)\s+at_least\s+(\d+)\s+['\"](\w+)['\"])"
        
        def replace_condition3(match):
            full = match.group(1)
            days = int(match.group(2))
            device = match.group(3)
            threshold = int(match.group(4))
            event_name = match.group(5)
            
            start_time = now - days * 86400
            filters = {
                "user_id": user_id,
                "event_name": event_name,
                "timestamp": lambda t: t >= start_time
            }
            if device:
                filters["device_type"] = device
            
            events = self.storage.get_events(filters)
            count = len(events)
            result = count >= threshold
            
            return 'True' if result else 'False'
        
        eval_expr = expression
        eval_expr = re.sub(pattern3, replace_condition3, eval_expr, flags=re.IGNORECASE)
        eval_expr = re.sub(pattern2, replace_condition2, eval_expr, flags=re.IGNORECASE)
        eval_expr = re.sub(pattern, replace_condition, eval_expr, flags=re.IGNORECASE)
        
        eval_expr = re.sub(r'\bAND\b', 'and', eval_expr, flags=re.IGNORECASE)
        eval_expr = re.sub(r'\bOR\b', 'or', eval_expr, flags=re.IGNORECASE)
        
        try:
            result = eval(eval_expr, {"__builtins__": {}}, {})
            return bool(result)
        except Exception:
            return False


class SegmentModule:
    def __init__(self):
        self.storage = MemoryStorage()
        self.parser = SegmentExpressionParser()
        self.cohort_module = CohortModule()

    def create_segment(self, name: str, expression: str, 
                       description: str = None, 
                       subscribers: List[str] = None) -> Dict[str, Any]:
        validation = self.parser.validate_expression(expression)
        if not validation["valid"]:
            return {
                "success": False,
                "error": validation["error"],
                "suggestion": validation.get("suggestion")
            }
        
        segment = {
            "name": name,
            "expression": expression,
            "description": description,
            "subscribers": subscribers or [],
            "last_member_count": 0,
            "last_members": [],
            "last_updated": None
        }
        
        segment_id = self.storage.save_segment(segment)
        members = self.get_segment_members(segment_id)
        
        return {
            "success": True,
            "segment_id": segment_id,
            "preview_member_count": len(members),
            "preview_members": members[:50]
        }

    def get_segment_members(self, segment_id: str) -> List[str]:
        segment = self.storage.get_segment(segment_id)
        if not segment:
            return []
        
        evaluator = self.parser.parse_expression(segment["expression"])
        if not evaluator:
            return []
        
        members = []
        for user_id in self.storage.user_profiles.keys():
            if evaluator(user_id):
                members.append(user_id)
        
        segment["last_member_count"] = len(members)
        segment["last_members"] = members
        segment["last_updated"] = datetime.now().timestamp()
        self.storage.save_segment(segment)
        
        return members

    def validate_expression(self, expression: str) -> Dict[str, Any]:
        return self.parser.validate_expression(expression)

    def preview_segment(self, expression: str, limit: int = 50) -> Dict[str, Any]:
        validation = self.parser.validate_expression(expression)
        if not validation["valid"]:
            return {
                "success": False,
                "error": validation["error"],
                "suggestion": validation.get("suggestion")
            }
        
        evaluator = self.parser.parse_expression(expression)
        if not evaluator:
            return {"success": False, "error": "Failed to parse expression"}
        
        members = []
        for user_id in self.storage.user_profiles.keys():
            if evaluator(user_id):
                members.append(user_id)
                if len(members) >= limit * 2:
                    break
        
        return {
            "success": True,
            "expression": expression,
            "estimated_count": len(members),
            "preview_members": members[:limit]
        }

    def compare_segments(self, segment_ids: List[str], 
                         metrics: List[str] = None) -> Dict[str, Any]:
        metrics = metrics or ['retention', 'active_frequency', 'aov']
        
        segment_data = {}
        all_members = set()
        
        for segment_id in segment_ids:
            segment = self.storage.get_segment(segment_id)
            if not segment:
                continue
            
            members = self.get_segment_members(segment_id)
            all_members.update(members)
            
            segment_metrics = {}
            users = [self.storage.get_user(uid) for uid in members]
            users = [u for u in users if u is not None]
            
            if 'retention' in metrics:
                retention = self.cohort_module.get_retention_curve(members)
                segment_metrics['retention'] = retention
            
            if 'active_frequency' in metrics:
                now = datetime.now().timestamp()
                thirty_days_ago = now - 30 * 86400
                frequencies = []
                for user in users:
                    events = self.storage.get_events({
                        "user_id": user['user_id'],
                        "timestamp": lambda t: t >= thirty_days_ago
                    })
                    frequencies.append(len(events))
                
                if frequencies:
                    segment_metrics['active_frequency'] = {
                        "avg": round(sum(frequencies) / len(frequencies), 2),
                        "median": sorted(frequencies)[len(frequencies) // 2],
                        "p75": sorted(frequencies)[int(len(frequencies) * 0.75)],
                        "p90": sorted(frequencies)[int(len(frequencies) * 0.9)]
                    }
                else:
                    segment_metrics['active_frequency'] = None
            
            if 'aov' in metrics:
                spending_users = [u for u in users if u.get('total_spent', 0) > 0]
                if spending_users:
                    aov_values = [u['total_spent'] / max(1, u.get('order_count', 1)) for u in spending_users]
                    segment_metrics['aov'] = {
                        "avg": round(sum(aov_values) / len(aov_values), 2),
                        "median": round(sorted(aov_values)[len(aov_values) // 2], 2),
                        "total_spent": round(sum(u['total_spent'] for u in spending_users), 2),
                        "order_count": sum(u.get('order_count', 0) for u in spending_users),
                        "paying_users": len(spending_users)
                    }
                else:
                    segment_metrics['aov'] = None
            
            segment_data[segment_id] = {
                "name": segment.get('name', segment_id),
                "member_count": len(members),
                "members": members,
                "metrics": segment_metrics
            }
        
        comparison = self._generate_comparison_conclusions(segment_data, metrics)
        
        return {
            "success": True,
            "segment_ids": segment_ids,
            "metrics": metrics,
            "segment_data": segment_data,
            "comparison": comparison
        }

    def _generate_comparison_conclusions(self, segment_data: Dict[str, Any], 
                                          metrics: List[str]) -> List[str]:
        conclusions = []
        segments = list(segment_data.keys())
        
        if len(segments) < 2:
            return conclusions
        
        for metric in metrics:
            if metric == 'retention':
                best_seg = None
                best_rate = -1
                worst_seg = None
                worst_rate = float('inf')
                
                for seg_id, data in segment_data.items():
                    retention = data['metrics'].get('retention', {})
                    if retention.get('success'):
                        curve = retention.get('curve', [])
                        if curve:
                            d7_rate = next((c['retention_rate'] for c in curve if c['period_days'] == 7), None)
                            if d7_rate is not None:
                                if d7_rate > best_rate:
                                    best_rate = d7_rate
                                    best_seg = (seg_id, data['name'], d7_rate)
                                if d7_rate < worst_rate:
                                    worst_rate = d7_rate
                                    worst_seg = (seg_id, data['name'], d7_rate)
                
                if best_seg and worst_seg and best_seg[0] != worst_seg[0]:
                    diff_pct = (best_rate - worst_rate) / worst_rate * 100 if worst_rate > 0 else 0
                    conclusions.append(
                        f"7日留存对比：{best_seg[1]} ({best_rate:.1%}) 比 {worst_seg[1]} ({worst_rate:.1%}) 高 {diff_pct:.1f}%"
                    )
            
            elif metric == 'active_frequency':
                freqs = []
                for seg_id, data in segment_data.items():
                    freq = data['metrics'].get('active_frequency')
                    if freq:
                        freqs.append((seg_id, data['name'], freq['avg']))
                
                if len(freqs) >= 2:
                    freqs.sort(key=lambda x: -x[2])
                    highest = freqs[0]
                    lowest = freqs[-1]
                    if highest[2] > 0:
                        diff_pct = (highest[2] - lowest[2]) / lowest[2] * 100 if lowest[2] > 0 else 0
                        conclusions.append(
                            f"30天活跃频次对比：{highest[1]} (平均{highest[2]:.1f}次) 比 {lowest[1]} (平均{lowest[2]:.1f}次) 高 {diff_pct:.1f}%"
                        )
            
            elif metric == 'aov':
                aovs = []
                for seg_id, data in segment_data.items():
                    aov = data['metrics'].get('aov')
                    if aov:
                        aovs.append((seg_id, data['name'], aov['avg']))
                
                if len(aovs) >= 2:
                    aovs.sort(key=lambda x: -x[2])
                    highest = aovs[0]
                    lowest = aovs[-1]
                    if highest[2] > 0:
                        diff_pct = (highest[2] - lowest[2]) / lowest[2] * 100 if lowest[2] > 0 else 0
                        conclusions.append(
                            f"客单价对比：{highest[1]} (¥{highest[2]:.2f}) 比 {lowest[1]} (¥{lowest[2]:.2f}) 高 {diff_pct:.1f}%"
                        )
        
        return conclusions

    def check_and_notify_subscribers(self, segment_id: str) -> Dict[str, Any]:
        segment = self.storage.get_segment(segment_id)
        if not segment:
            return {"success": False, "error": "Segment not found"}
        
        old_members = set(segment.get('last_members', []))
        new_members = set(self.get_segment_members(segment_id))
        
        added = list(new_members - old_members)
        removed = list(old_members - new_members)
        
        if added or removed:
            subscribers = segment.get('subscribers', [])
            for subscriber in subscribers:
                print(f"Notifying {subscriber}: Segment {segment['name']} changed - added {len(added)}, removed {len(removed)}")
            
            return {
                "success": True,
                "changed": True,
                "added": added,
                "removed": removed,
                "notified_subscribers": subscribers
            }
        
        return {
            "success": True,
            "changed": False
        }

    def list_segments(self) -> List[Dict[str, Any]]:
        segments = self.storage.get_all_segments()
        result = []
        for seg in segments:
            result.append({
                "segment_id": seg.get('segment_id'),
                "name": seg.get('name'),
                "description": seg.get('description'),
                "expression": seg.get('expression'),
                "member_count": seg.get('last_member_count', 0),
                "subscriber_count": len(seg.get('subscribers', [])),
                "created_at": seg.get('created_at'),
                "last_updated": seg.get('last_updated')
            })
        return result

    def delete_segment(self, segment_id: str) -> Dict[str, Any]:
        success = self.storage.delete_segment(segment_id)
        return {"success": success}
