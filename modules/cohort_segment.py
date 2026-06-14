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

DEVICE_ALIASES = {
    'ios': 'ios', 'IOS': 'ios', 'iOS': 'ios', '苹果': 'ios',
    'android': 'android', 'ANDROID': 'android', '安卓': 'android',
    'web': 'web', 'WEB': 'web', 'h5': 'web', 'H5': 'web',
    'mp': 'mp', 'MP': 'mp', 'wechat': 'mp', 'weixin': 'mp', '小程序': 'mp',
    'wx': 'wx', 'WX': 'wx', 'official': 'wx', '公众号': 'wx',
}

VALID_DEVICES = {'ios', 'android', 'web', 'mp', 'wx'}

class SegmentExpressionParser:
    _OPERATORS = {
        'AND': all, 'and': all, '且': all, '并且': all,
        'OR': any, 'or': any, '或': any, '或者': any,
    }
    
    _COMPARISONS = {
        '>': operator.gt, '大于': operator.gt, '超过': operator.gt, '多于': operator.gt, 'more_than': operator.gt,
        '<': operator.lt, '小于': operator.lt, '低于': operator.lt, '少于': operator.lt, 'less_than': operator.lt,
        '>=': operator.ge, '大于等于': operator.ge, '不少于': operator.ge, '至少': operator.ge, '不低于': operator.ge, 'at_least': operator.ge,
        '<=': operator.le, '小于等于': operator.le, '不多于': operator.le, '至多': operator.le, '不超过': operator.le, 'at_most': operator.le,
        '==': operator.eq, '=': operator.eq, '等于': operator.eq, '=': operator.eq,
        '!=': operator.ne, '不等于': operator.ne,
        'contains': lambda a, b: b in str(a).lower() if a else False,
        'in': lambda a, b: a in b if isinstance(b, (list, set, tuple)) else a == b,
        'not in': lambda a, b: a not in b if isinstance(b, (list, set, tuple)) else a != b,
    }

    def __init__(self):
        self.storage = MemoryStorage()

    def _normalize_device(self, device: str) -> Optional[str]:
        if not device:
            return None
        device = device.strip().strip('"\'')
        return DEVICE_ALIASES.get(device, device.lower())

    def _preprocess_expression(self, expression: str) -> str:
        expr = ' ' + expression.strip() + ' '
        
        expr = re.sub(r'过去\s*(\d+)\s*天', r' past \1 days ', expr)
        expr = re.sub(r'最近\s*(\d+)\s*天', r' past \1 days ', expr)
        expr = re.sub(r'近\s*(\d+)\s*天', r' past \1 days ', expr)
        
        def replace_device_multi(match):
            device_part = match.group(1).strip()
            device_part = device_part.replace('，', ',').strip()
            return f' in [{device_part}] '
        
        def replace_device_single(match):
            device_part = match.group(1).strip()
            device_part = device_part.strip('"\'').strip()
            return f" in '{device_part}' "
        
        expr = re.sub(r'在\s*\(\s*([^)]+?)\s*\)\s*端', replace_device_multi, expr)
        expr = re.sub(r'在\s*\[([^\]]+?)\]\s*端', replace_device_multi, expr)
        expr = re.sub(r'在\s*(\S+?)\s*端', replace_device_single, expr)
        
        expr = re.sub(r'浏览过', r' event_count "page_view" ', expr)
        expr = re.sub(r'浏览了', r' event_count "page_view" ', expr)
        
        expr = re.sub(r'完成过至少\s*(\d+)\s*次订单', lambda m: f' event_count "order_completed" >= {m.group(1)} ', expr)
        expr = re.sub(r'完成了\s*(\d+)\s*次订单', lambda m: f' event_count "order_completed" >= {m.group(1)} ', expr)
        expr = re.sub(r'完成过订单', r' event_count "order_completed" >= 1 ', expr)
        expr = re.sub(r'完成过至少\s*(\d+)\s*次', lambda m: f' >= {m.group(1)} ', expr)
        
        expr = re.sub(r'加购过', r' event_count "add_to_cart" ', expr)
        expr = re.sub(r'登录过', r' event_count "login" ', expr)
        
        expr = re.sub(r'有\s*(\d+)\s*次以上', lambda m: f' > {m.group(1)} ', expr)
        expr = re.sub(r'有\s*(\d+)\s*次', lambda m: f' >= {m.group(1)} ', expr)
        expr = re.sub(r'至少\s*(\d+)\s*次', lambda m: f' >= {m.group(1)} ', expr)
        expr = re.sub(r'不少于\s*(\d+)\s*次', lambda m: f' >= {m.group(1)} ', expr)
        expr = re.sub(r'超过\s*(\d+)\s*次', lambda m: f' > {m.group(1)} ', expr)
        expr = re.sub(r'多于\s*(\d+)\s*次', lambda m: f' > {m.group(1)} ', expr)
        expr = re.sub(r'少于\s*(\d+)\s*次', lambda m: f' < {m.group(1)} ', expr)
        expr = re.sub(r'至多\s*(\d+)\s*次', lambda m: f' <= {m.group(1)} ', expr)
        
        expr = re.sub(r'\b且\b', ' AND ', expr)
        expr = re.sub(r'\b并且\b', ' AND ', expr)
        expr = re.sub(r'\b或\b', ' OR ', expr)
        expr = re.sub(r'\b或者\b', ' OR ', expr)
        
        expr = re.sub(r'\s+', ' ', expr).strip()
        
        return expr

    def _parse_condition(self, condition_str: str) -> Optional[Dict[str, Any]]:
        condition_str = condition_str.strip()
        if not condition_str:
            return None
        
        pattern = (
            r'(?:past|过去)\s+(\d+)\s+(?:days|天)'
            r'(?:\s+in\s+(.+?))?'
            r'\s+(?:event_count|has|completed|有|浏览过|完成过)'
            r'\s+(.+?)(?=\s*(?:>=|<=|>|<|==|!=|=|至少|大于|小于|不少于|不多于|超过|少于|等于|不等于))'
            r'\s*(>=|<=|>|<|==|!=|=|至少|大于|小于|不少于|不多于|超过|少于|等于|不等于)'
            r'\s*(\d+)'
        )
        
        match = re.match(pattern, condition_str, re.IGNORECASE)
        if match:
            days = int(match.group(1))
            device_spec = match.group(2)
            event_name = match.group(3).strip().strip('"\'').lower()
            op = match.group(4).strip()
            threshold = int(match.group(5))
            
            devices = None
            if device_spec:
                device_spec = device_spec.strip()
                device_match = re.match(r'^\s*[\[\(\{](.+)[\]\)\}]\s*$', device_spec)
                if device_match:
                    device_list = [d.strip().strip('"\'') for d in device_match.group(1).replace('，', ',').split(',')]
                    devices = [self._normalize_device(d) for d in device_list if self._normalize_device(d) in VALID_DEVICES]
                else:
                    single_device = self._normalize_device(device_spec.strip().strip('"\''))
                    if single_device and single_device in VALID_DEVICES:
                        devices = [single_device]
            
            op_lower = op.lower()
            for op_key in self._COMPARISONS:
                if op_lower == op_key.lower():
                    op = op_key
                    break
            
            return {
                'type': 'event_count',
                'days': days,
                'devices': devices,
                'event_name': event_name,
                'operator': op,
                'threshold': threshold
            }
        
        return None

    def _tokenize(self, expression: str) -> List[str]:
        tokens = []
        i = 0
        while i < len(expression):
            if expression[i] in '()[],':
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
            elif expression[i] in '>!=<':
                j = i
                while j < len(expression) and expression[j] in '>!=<':
                    j += 1
                tokens.append(expression[i:j])
                i = j
            else:
                j = i
                while j < len(expression) and not expression[j].isspace() and expression[j] not in '()[],<>!=':
                    j += 1
                tokens.append(expression[i:j])
                i = j
        return tokens

    def validate_expression(self, expression: str) -> Dict[str, Any]:
        try:
            processed = self._preprocess_expression(expression)
            
            tokens = self._tokenize(processed)
            
            conditions = []
            operators = []
            i = 0
            
            while i < len(tokens):
                token = tokens[i]
                
                if token.upper() in ['AND', 'OR']:
                    operators.append(token.upper())
                    i += 1
                elif token in '()[],':
                    i += 1
                elif token.lower() in ['past', '过去']:
                    condition_tokens = [token]
                    i += 1
                    while i < len(tokens) and tokens[i].upper() not in ['AND', 'OR'] and tokens[i] not in '()':
                        condition_tokens.append(tokens[i])
                        i += 1
                    
                    condition_str = ' '.join(condition_tokens)
                    condition = self._parse_condition(condition_str)
                    
                    if condition:
                        conditions.append(condition)
                    else:
                        return {
                            "valid": False,
                            "error": f"无法解析条件: {condition_str}",
                            "suggestion": "请检查格式，例如: 过去30天在'ios'端浏览过至少3次 AND 在'web'端完成过至少1次订单"
                        }
                else:
                    i += 1
            
            if not conditions:
                return {
                    "valid": False,
                    "error": "未找到有效的查询条件",
                    "suggestion": "示例1: past 30 days in 'ios' event_count 'page_view' >= 3 AND past 30 days in 'web' event_count 'order_completed' >= 1\n示例2: 过去30天在'ios'端浏览过至少3次 且 在'web'端完成过至少1次订单"
                }
            
            expected_operators = len(conditions) - 1
            if len(operators) != expected_operators and len(conditions) > 1:
                return {
                    "valid": False,
                    "error": f"条件与运算符数量不匹配: {len(conditions)}个条件需要 {expected_operators} 个运算符，当前有 {len(operators)} 个",
                    "suggestion": "请使用 AND/且 或 OR/或 连接多个条件"
                }
            
            return {"valid": True, "processed": processed, "conditions": conditions, "operators": operators}
            
        except Exception as e:
            return {
                "valid": False,
                "error": f"表达式语法错误: {str(e)}",
                "suggestion": "示例1: past 30 days in 'ios' event_count 'page_view' >= 3 AND past 30 days in 'web' event_count 'order_completed' >= 1\n示例2: 过去30天在'ios'端浏览过至少3次 且 在'web'端完成过至少1次订单"
            }

    def parse_expression(self, expression: str) -> Optional[Callable[[str], bool]]:
        validation = self.validate_expression(expression)
        if not validation["valid"]:
            return None
        
        try:
            conditions = validation.get("conditions", [])
            operators = validation.get("operators", [])
            
            def evaluate(user_id: str) -> bool:
                now = self.storage.get_effective_now()
                results = []
                
                for cond in conditions:
                    start_time = now - cond['days'] * 86400
                    filters = {
                        "user_id": user_id,
                        "event_name": cond['event_name'],
                        "timestamp": lambda t: t >= start_time
                    }
                    
                    if cond['devices']:
                        filters["device_type"] = cond['devices']
                    
                    events = self.storage.get_events(filters)
                    count = len(events)
                    
                    op_func = self._COMPARISONS.get(cond['operator'])
                    if op_func:
                        results.append(op_func(count, cond['threshold']))
                    else:
                        results.append(False)
                
                if not results:
                    return False
                if len(results) == 1:
                    return results[0]
                
                final_result = results[0]
                for i, op in enumerate(operators):
                    op_func = self._OPERATORS.get(op, all)
                    if op == 'AND' or op == '且':
                        final_result = final_result and results[i + 1]
                    elif op == 'OR' or op == '或':
                        final_result = final_result or results[i + 1]
                
                return final_result
            
            return evaluate
        except Exception:
            return None


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
