import math
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from .storage import MemoryStorage

VALID_GRANULARITIES = {'day', 'week', 'month'}
VALID_PERIODS = {1, 3, 7, 14, 30, 60, 90}
MIN_COHORT_SIZE = 10
REGISTER_CHANNELS = {'promotion', 'ad', 'invite', 'natural'}
USER_LEVELS = {'vip', 'normal'}
FIRST_DEVICES = {'ios', 'android', 'web'}

class CohortModule:
    def __init__(self):
        self.storage = MemoryStorage()

    def _truncate_time(self, timestamp: float, granularity: str) -> float:
        dt = datetime.fromtimestamp(timestamp)
        if granularity == 'day':
            dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        elif granularity == 'week':
            dt = dt - timedelta(days=dt.weekday())
            dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        elif granularity == 'month':
            dt = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return dt.timestamp()

    def _format_cohort_label(self, timestamp: float, granularity: str) -> str:
        dt = datetime.fromtimestamp(timestamp)
        if granularity == 'day':
            return dt.strftime('%Y-%m-%d')
        elif granularity == 'week':
            end_dt = dt + timedelta(days=6)
            return f"{dt.strftime('%Y-%m-%d')}~{end_dt.strftime('%Y-%m-%d')}"
        elif granularity == 'month':
            return dt.strftime('%Y-%m')

    def _calculate_confidence_interval(self, retained: int, total: int) -> Optional[Dict[str, float]]:
        if total == 0:
            return None
        p = retained / total
        z = 1.96
        if total < 30:
            n = total
            lower = (p + z * z / (2 * n) - z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / (1 + z * z / n)
            upper = (p + z * z / (2 * n) + z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / (1 + z * z / n)
            lower = max(0, lower)
            upper = min(1, upper)
            margin = (upper - lower) / 2
            return {
                "lower": round(lower, 4),
                "upper": round(upper, 4),
                "margin": round(margin, 4),
                "method": "wilson"
            }
        se = math.sqrt(p * (1 - p) / total)
        return {
            "lower": round(max(0, p - z * se), 4),
            "upper": round(min(1, p + z * se), 4),
            "margin": round(z * se, 4),
            "method": "wald"
        }

    def analyze(self, granularity: str = 'day', periods: List[int] = None,
                segment_by: str = None, segment_values: List[str] = None,
                min_cohort_size: int = MIN_COHORT_SIZE,
                start_date: float = None, end_date: float = None) -> Dict[str, Any]:
        if granularity not in VALID_GRANULARITIES:
            return {"success": False, "error": f"Invalid granularity. Must be one of {VALID_GRANULARITIES}"}
        
        periods = periods or [1, 3, 7, 14, 30]
        periods = sorted([p for p in periods if p in VALID_PERIODS])
        if not periods:
            return {"success": False, "error": f"No valid periods. Must be subset of {VALID_PERIODS}"}

        users = self.storage.get_users()
        if start_date:
            users = [u for u in users if u['first_active'] >= start_date]
        if end_date:
            users = [u for u in users if u['first_active'] <= end_date]

        if segment_by:
            if segment_by == 'register_channel':
                valid_values = REGISTER_CHANNELS
                user_key = 'register_channel'
            elif segment_by == 'user_level':
                valid_values = USER_LEVELS
                user_key = 'user_level'
            elif segment_by == 'first_device':
                valid_values = FIRST_DEVICES
                user_key = 'first_device'
            else:
                return {"success": False, "error": f"Invalid segment_by. Must be register_channel, user_level, or first_device"}
            
            if segment_values:
                segment_values = [v for v in segment_values if v in valid_values]
            else:
                segment_values = list(valid_values)
            
            if not segment_values:
                return {"success": False, "error": f"No valid segment values. Must be subset of {valid_values}"}

        user_events: Dict[str, List[float]] = {}
        for event in self.storage.get_events():
            uid = event['user_id']
            if uid not in user_events:
                user_events[uid] = []
            user_events[uid].append(event['timestamp'])

        cohorts: Dict[str, Dict[str, Any]] = {}
        for user in users:
            if segment_by:
                seg_val = user.get(user_key)
                if seg_val not in segment_values:
                    continue
                cohort_key = f"{self._truncate_time(user['first_active'], granularity)}_{seg_val}"
            else:
                cohort_key = str(self._truncate_time(user['first_active'], granularity))
            
            if cohort_key not in cohorts:
                ts = self._truncate_time(user['first_active'], granularity)
                cohorts[cohort_key] = {
                    "cohort_timestamp": ts,
                    "cohort_label": self._format_cohort_label(ts, granularity),
                    "segment": user.get(user_key) if segment_by else None,
                    "users": set(),
                    "user_count": 0
                }
            cohorts[cohort_key]["users"].add(user['user_id'])
            cohorts[cohort_key]["user_count"] += 1

        cohort_list = sorted(
            [c for c in cohorts.values() if c["user_count"] >= min_cohort_size],
            key=lambda c: c["cohort_timestamp"]
        )

        filtered_count = len([c for c in cohorts.values() if c["user_count"] < min_cohort_size])

        matrix = []
        for cohort in cohort_list:
            row = {
                "cohort_label": cohort["cohort_label"],
                "cohort_timestamp": cohort["cohort_timestamp"],
                "segment": cohort["segment"],
                "user_count": cohort["user_count"],
                "periods": []
            }
            
            for period in periods:
                period_seconds = period * 86400
                window_start = cohort["cohort_timestamp"] + period_seconds
                window_end = window_start + self._get_granularity_seconds(granularity)
                
                retained = 0
                for uid in cohort["users"]:
                    events = user_events.get(uid, [])
                    for evt_ts in events:
                        if evt_ts >= window_start and evt_ts < window_end:
                            retained += 1
                            break
                
                retention_rate = retained / cohort["user_count"] if cohort["user_count"] > 0 else 0
                ci = self._calculate_confidence_interval(retained, cohort["user_count"])
                
                row["periods"].append({
                    "period_days": period,
                    "retained_users": retained,
                    "retention_rate": round(retention_rate, 4),
                    "confidence_interval": ci,
                    "small_sample": cohort["user_count"] < MIN_COHORT_SIZE * 2
                })
            
            matrix.append(row)

        return {
            "success": True,
            "granularity": granularity,
            "periods": periods,
            "segment_by": segment_by,
            "segment_values": segment_values,
            "min_cohort_size": min_cohort_size,
            "filtered_small_cohorts": filtered_count,
            "total_cohorts": len(cohort_list),
            "matrix": matrix
        }

    def _get_granularity_seconds(self, granularity: str) -> int:
        if granularity == 'day':
            return 86400
        elif granularity == 'week':
            return 604800
        elif granularity == 'month':
            return 2592000

    def compare_cohorts(self, analysis_result: Dict[str, Any], 
                        base_segment: str, compare_segment: str,
                        period: int) -> Dict[str, Any]:
        if not analysis_result.get("success"):
            return {"success": False, "error": "Invalid analysis result"}
        
        if not analysis_result.get("segment_by"):
            return {"success": False, "error": "Analysis must be segmented to compare"}
        
        matrix = analysis_result["matrix"]
        comparison = []
        
        for row in matrix:
            if row["segment"] == base_segment:
                base_rate = next((p["retention_rate"] for p in row["periods"] if p["period_days"] == period), None)
                base_retained = next((p["retained_users"] for p in row["periods"] if p["period_days"] == period), None)
                comparison.append({
                    "cohort_label": row["cohort_label"],
                    "cohort_timestamp": row["cohort_timestamp"],
                    "segment": base_segment,
                    "user_count": row["user_count"],
                    "retained_users": base_retained,
                    "retention_rate": base_rate
                })
            elif row["segment"] == compare_segment:
                comp_rate = next((p["retention_rate"] for p in row["periods"] if p["period_days"] == period), None)
                comp_retained = next((p["retained_users"] for p in row["periods"] if p["period_days"] == period), None)
                for item in comparison:
                    if item["cohort_label"] == row["cohort_label"] and item["segment"] == base_segment:
                        item["compare_segment"] = compare_segment
                        item["compare_user_count"] = row["user_count"]
                        item["compare_retained_users"] = comp_retained
                        item["compare_retention_rate"] = comp_rate
                        if item["retention_rate"] and comp_rate:
                            item["absolute_diff"] = round(comp_rate - item["retention_rate"], 4)
                            item["relative_diff_pct"] = round((comp_rate - item["retention_rate"]) / item["retention_rate"] * 100, 2) if item["retention_rate"] > 0 else None
                        break
        
        conclusions = self._generate_comparison_conclusions(comparison, base_segment, compare_segment, period)
        
        return {
            "success": True,
            "base_segment": base_segment,
            "compare_segment": compare_segment,
            "period_days": period,
            "comparison": comparison,
            "conclusions": conclusions
        }

    def _generate_comparison_conclusions(self, comparison: List[Dict[str, Any]],
                                          base_segment: str, compare_segment: str,
                                          period: int) -> List[str]:
        conclusions = []
        valid_comparisons = [c for c in comparison if "relative_diff_pct" in c and c["relative_diff_pct"] is not None]
        
        if not valid_comparisons:
            return conclusions
        
        avg_relative = sum(c["relative_diff_pct"] for c in valid_comparisons) / len(valid_comparisons)
        avg_absolute = sum(c["absolute_diff"] for c in valid_comparisons) / len(valid_comparisons)
        
        if avg_relative > 0:
            conclusions.append(
                f"{compare_segment} 来源用户 {period} 日留存平均比 {base_segment} 高 {abs(avg_relative):.1f}% "
                f"(绝对值高 {abs(avg_absolute):.1%})"
            )
        elif avg_relative < 0:
            conclusions.append(
                f"{compare_segment} 来源用户 {period} 日留存平均比 {base_segment} 低 {abs(avg_relative):.1f}% "
                f"(绝对值低 {abs(avg_absolute):.1%})"
            )
        else:
            conclusions.append(
                f"{compare_segment} 和 {base_segment} 来源用户 {period} 日留存基本持平"
            )
        
        best = max(valid_comparisons, key=lambda c: c["relative_diff_pct"])
        worst = min(valid_comparisons, key=lambda c: c["relative_diff_pct"])
        
        if best["relative_diff_pct"] > 10:
            conclusions.append(
                f"最大差距出现在 {best['cohort_label']} 队列，{compare_segment} 比 {base_segment} 高 {best['relative_diff_pct']:.1f}%"
            )
        if worst["relative_diff_pct"] < -10:
            conclusions.append(
                f"最小差距出现在 {worst['cohort_label']} 队列，{compare_segment} 比 {base_segment} 低 {abs(worst['relative_diff_pct']):.1f}%"
            )
        
        return conclusions

    def get_retention_curve(self, user_ids: List[str], periods: List[int] = None) -> Dict[str, Any]:
        periods = periods or [1, 3, 7, 14, 30, 60, 90]
        periods = sorted([p for p in periods if p in VALID_PERIODS])
        
        users = [self.storage.get_user(uid) for uid in user_ids]
        users = [u for u in users if u is not None]
        
        if not users:
            return {"success": False, "error": "No valid users"}
        
        user_events: Dict[str, List[float]] = {}
        for event in self.storage.get_events({"user_id": user_ids}):
            uid = event['user_id']
            if uid not in user_events:
                user_events[uid] = []
            user_events[uid].append(event['timestamp'])
        
        curve = []
        total_users = len(users)
        
        for period in periods:
            period_seconds = period * 86400
            retained = 0
            
            for user in users:
                first_active = user['first_active']
                window_start = first_active + period_seconds
                window_end = window_start + 86400
                
                events = user_events.get(user['user_id'], [])
                for evt_ts in events:
                    if evt_ts >= window_start and evt_ts < window_end:
                        retained += 1
                        break
            
            retention_rate = retained / total_users if total_users > 0 else 0
            ci = self._calculate_confidence_interval(retained, total_users)
            
            curve.append({
                "period_days": period,
                "retained_users": retained,
                "total_users": total_users,
                "retention_rate": round(retention_rate, 4),
                "confidence_interval": ci
            })
        
        return {
            "success": True,
            "total_users": total_users,
            "curve": curve
        }
