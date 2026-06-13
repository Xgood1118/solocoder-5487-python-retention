from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
from .storage import MemoryStorage

DEVICE_COLORS = {
    'ios': '#4CD964',
    'android': '#34C759',
    'web': '#007AFF',
    'mp': '#5856D6',
    'wx': '#FF9500'
}

CONVERSION_EVENTS = {
    'add_to_cart',
    'order_created',
    'order_completed',
    'payment_completed'
}

class CrossDeviceModule:
    def __init__(self):
        self.storage = MemoryStorage()

    def get_user_timeline(self, user_id: str, 
                          start_time: float = None, 
                          end_time: float = None) -> Dict[str, Any]:
        user = self.storage.get_user(user_id)
        if not user:
            return {"success": False, "error": f"User {user_id} not found"}

        events = self.storage.get_events({"user_id": user_id})
        if start_time:
            events = [e for e in events if e['timestamp'] >= start_time]
        if end_time:
            events = [e for e in events if e['timestamp'] <= end_time]

        events = sorted(events, key=lambda e: e['timestamp'])

        timeline = []
        for event in events:
            device = event.get('device_type', 'unknown')
            timeline.append({
                "timestamp": event['timestamp'],
                "datetime": datetime.fromtimestamp(event['timestamp']).isoformat(),
                "device_type": device,
                "product_line": event.get('product_line'),
                "event_name": event['event_name'],
                "properties": event.get('properties', {}),
                "color": DEVICE_COLORS.get(device, '#8E8E93'),
                "event_id": event.get('event_id')
            })

        device_switch_points = []
        prev_device = None
        for idx, event in enumerate(events):
            curr_device = event.get('device_type')
            if prev_device and curr_device != prev_device:
                device_switch_points.append({
                    "index": idx,
                    "timestamp": event['timestamp'],
                    "from_device": prev_device,
                    "to_device": curr_device
                })
            prev_device = curr_device

        return {
            "success": True,
            "user_id": user_id,
            "user_profile": {
                "first_active": user['first_active'],
                "last_active": user['last_active'],
                "devices": user['devices'],
                "total_events": user['total_events'],
                "register_channel": user.get('register_channel'),
                "user_level": user.get('user_level')
            },
            "total_events": len(timeline),
            "device_switches": len(device_switch_points),
            "switch_points": device_switch_points,
            "device_colors": DEVICE_COLORS,
            "timeline": timeline
        }

    def get_switch_frequency(self, start_time: float = None, 
                             end_time: float = None,
                             min_events: int = 5) -> Dict[str, Any]:
        events = self.storage.get_events()
        if start_time:
            events = [e for e in events if e['timestamp'] >= start_time]
        if end_time:
            events = [e for e in events if e['timestamp'] <= end_time]

        user_device_sequences: Dict[str, List[str]] = defaultdict(list)
        user_event_counts: Dict[str, int] = defaultdict(int)
        for event in sorted(events, key=lambda e: e['timestamp']):
            uid = event['user_id']
            device = event.get('device_type')
            user_event_counts[uid] += 1
            if device and (not user_device_sequences[uid] or user_device_sequences[uid][-1] != device):
                user_device_sequences[uid].append(device)

        user_switches = {}
        for uid, devices in user_device_sequences.items():
            if user_event_counts[uid] >= min_events:
                switch_count = len(devices) - 1
                user_switches[uid] = {
                    "device_count": len(set(devices)),
                    "switch_count": switch_count,
                    "switch_frequency": switch_count / max(1, len(devices)),
                    "total_events": user_event_counts[uid]
                }

        if not user_switches:
            return {"success": True, "total_users": 0, "distribution": {}}

        switch_counts = [v['switch_count'] for v in user_switches.values()]
        device_counts = [v['device_count'] for v in user_switches.values()]

        distribution = {
            "0_switches": sum(1 for c in switch_counts if c == 0),
            "1-2_switches": sum(1 for c in switch_counts if 1 <= c <= 2),
            "3-5_switches": sum(1 for c in switch_counts if 3 <= c <= 5),
            "6+_switches": sum(1 for c in switch_counts if c >= 6)
        }

        device_distribution = {}
        for dc in device_counts:
            key = f"{dc}_devices"
            device_distribution[key] = device_distribution.get(key, 0) + 1

        percentiles = self._calculate_percentiles(switch_counts)
        single_device_pct = (device_distribution.get('1_devices', 0) / len(user_switches)) * 100
        multi_device_pct = 100 - single_device_pct

        return {
            "success": True,
            "total_users": len(user_switches),
            "min_events_threshold": min_events,
            "switch_count_distribution": distribution,
            "device_count_distribution": device_distribution,
            "single_device_users_pct": round(single_device_pct, 2),
            "multi_device_users_pct": round(multi_device_pct, 2),
            "avg_switches_per_user": round(sum(switch_counts) / len(switch_counts), 2),
            "max_switches": max(switch_counts),
            "percentiles": percentiles,
            "observation": f"{single_device_pct:.1f}% 用户只用单一端，{multi_device_pct:.1f}% 用户跨端使用"
        }

    def _calculate_percentiles(self, values: List[float]) -> Dict[str, float]:
        if not values:
            return {}
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        return {
            "p25": sorted_vals[int(n * 0.25)],
            "p50": sorted_vals[int(n * 0.5)],
            "p75": sorted_vals[int(n * 0.75)],
            "p90": sorted_vals[int(n * 0.9)],
            "p95": sorted_vals[int(n * 0.95)]
        }

    def get_duration_distribution(self, start_time: float = None,
                                  end_time: float = None,
                                  session_timeout: int = 1800) -> Dict[str, Any]:
        events = self.storage.get_events()
        if start_time:
            events = [e for e in events if e['timestamp'] >= start_time]
        if end_time:
            events = [e for e in events if e['timestamp'] <= end_time]

        user_events: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for event in events:
            user_events[event['user_id']].append(event)

        device_durations: Dict[str, List[float]] = defaultdict(list)
        device_sessions: Dict[str, int] = defaultdict(int)

        for uid, user_evts in user_events.items():
            user_evts = sorted(user_evts, key=lambda e: e['timestamp'])
            
            sessions: Dict[str, List[float]] = defaultdict(list)
            for event in user_evts:
                device = event.get('device_type')
                if not device:
                    continue
                ts = event['timestamp']
                
                if not sessions[device] or ts - sessions[device][-1] > session_timeout:
                    sessions[device].append(ts)
                    sessions[device].append(ts)
                    device_sessions[device] += 1
                else:
                    sessions[device][-1] = ts

            for device, times in sessions.items():
                for i in range(0, len(times), 2):
                    if i + 1 < len(times):
                        duration = times[i + 1] - times[i]
                        if duration == 0:
                            duration = 30
                        device_durations[device].append(duration)

        result = {}
        for device in ['ios', 'android', 'web', 'mp', 'wx']:
            durations = device_durations.get(device, [])
            if durations:
                result[device] = {
                    "total_sessions": device_sessions.get(device, 0),
                    "total_minutes": round(sum(durations) / 60, 2),
                    "avg_session_minutes": round((sum(durations) / len(durations)) / 60, 2),
                    "median_session_minutes": round(sorted(durations)[len(durations) // 2] / 60, 2),
                    "percentiles": {k: round(v / 60, 2) for k, v in self._calculate_percentiles(durations).items()}
                }
            else:
                result[device] = {
                    "total_sessions": 0,
                    "total_minutes": 0,
                    "avg_session_minutes": 0,
                    "median_session_minutes": 0,
                    "percentiles": {}
                }

        return {
            "success": True,
            "session_timeout_seconds": session_timeout,
            "by_device": result
        }

    def get_conversion_paths(self, start_time: float = None,
                             end_time: float = None,
                             funnel_steps: List[str] = None) -> Dict[str, Any]:
        funnel_steps = funnel_steps or ['add_to_cart', 'order_created', 'order_completed']
        
        events = self.storage.get_events({"event_name": funnel_steps})
        if start_time:
            events = [e for e in events if e['timestamp'] >= start_time]
        if end_time:
            events = [e for e in events if e['timestamp'] <= end_time]

        user_events: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for event in events:
            user_events[event['user_id']].append(event)

        path_counts: Dict[Tuple[str, ...], int] = defaultdict(int)
        device_transitions: Dict[Tuple[str, str, str], int] = defaultdict(int)

        for uid, evts in user_events.items():
            evts = sorted(evts, key=lambda e: e['timestamp'])
            
            funnel_progress = {}
            for event in evts:
                step_idx = funnel_steps.index(event['event_name'])
                device = event.get('device_type')
                
                if event['event_name'] not in funnel_progress:
                    funnel_progress[event['event_name']] = device
                    
                    if step_idx > 0:
                        prev_step = funnel_steps[step_idx - 1]
                        if prev_step in funnel_progress:
                            prev_device = funnel_progress[prev_step]
                            transition_key = (prev_step, prev_device, device)
                            device_transitions[transition_key] += 1

            path = tuple(funnel_progress.get(step) for step in funnel_steps)
            if all(path):
                path_counts[path] += 1

        transition_summary = []
        for (step, from_device, to_device), count in device_transitions.items():
            step_idx = funnel_steps.index(step)
            next_step = funnel_steps[step_idx + 1] if step_idx + 1 < len(funnel_steps) else None
            same_device = from_device == to_device
            transition_summary.append({
                "from_step": step,
                "to_step": next_step,
                "from_device": from_device,
                "to_device": to_device,
                "cross_device": not same_device,
                "count": count
            })

        path_summary = []
        total_paths = sum(path_counts.values())
        for path, count in sorted(path_counts.items(), key=lambda x: -x[1]):
            devices = list(path)
            cross_device = len(set(devices)) > 1
            path_summary.append({
                "path": list(zip(funnel_steps, devices)),
                "devices": devices,
                "cross_device": cross_device,
                "count": count,
                "percentage": round(count / total_paths * 100, 2) if total_paths > 0 else 0
            })

        return {
            "success": True,
            "funnel_steps": funnel_steps,
            "total_paths": total_paths,
            "cross_device_paths": sum(1 for p in path_counts if len(set(p)) > 1),
            "same_device_paths": sum(1 for p in path_counts if len(set(p)) == 1),
            "path_summary": path_summary[:20],
            "device_transitions": sorted(transition_summary, key=lambda t: -t['count'])
        }

    def analyze_funnel(self, funnel_definition: List[Dict[str, Any]],
                       start_time: float = None,
                       end_time: float = None) -> Dict[str, Any]:
        events = self.storage.get_events()
        if start_time:
            events = [e for e in events if e['timestamp'] >= start_time]
        if end_time:
            events = [e for e in events if e['timestamp'] <= end_time]

        user_events: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for event in events:
            user_events[event['user_id']].append(event)

        funnel_result = []
        previous_count = None

        for idx, step in enumerate(funnel_definition):
            step_name = step.get('name', f"step_{idx}")
            event_name = step.get('event_name')
            device_type = step.get('device_type')
            product_line = step.get('product_line')

            matching_users = set()
            for uid, evts in user_events.items():
                for event in evts:
                    match = True
                    if event_name and event['event_name'] != event_name:
                        match = False
                    if device_type and event.get('device_type') != device_type:
                        match = False
                    if product_line and event.get('product_line') != product_line:
                        match = False
                    
                    if match:
                        matching_users.add(uid)
                        break

            count = len(matching_users)
            conversion_rate = None
            if previous_count is not None and previous_count > 0:
                conversion_rate = round(count / previous_count, 4)

            overall_rate = None
            if funnel_result and funnel_result[0]['count'] > 0:
                overall_rate = round(count / funnel_result[0]['count'], 4)

            funnel_result.append({
                "step_index": idx,
                "step_name": step_name,
                "event_name": event_name,
                "device_type": device_type,
                "product_line": product_line,
                "count": count,
                "conversion_from_prev": conversion_rate,
                "conversion_from_start": overall_rate,
                "users": list(matching_users)
            })

            previous_count = count

        cross_device_analysis = self._analyze_funnel_cross_device(
            funnel_definition, user_events, funnel_result
        )

        return {
            "success": True,
            "funnel_steps": funnel_definition,
            "total_users": funnel_result[0]['count'] if funnel_result else 0,
            "final_conversion_rate": funnel_result[-1]['conversion_from_start'] if funnel_result and len(funnel_result) > 1 else None,
            "steps": [
                {k: v for k, v in step.items() if k != 'users'}
                for step in funnel_result
            ],
            "cross_device_analysis": cross_device_analysis
        }

    def _analyze_funnel_cross_device(self, funnel_definition: List[Dict[str, Any]],
                                     user_events: Dict[str, List[Dict[str, Any]]],
                                     funnel_result: List[Dict[str, Any]]) -> Dict[str, Any]:
        if len(funnel_definition) < 2:
            return {}

        completed_users = funnel_result[-1]['users'] if funnel_result else []
        
        transition_analysis = []
        for i in range(len(funnel_definition) - 1):
            step1 = funnel_definition[i]
            step2 = funnel_definition[i + 1]
            
            same_device = 0
            cross_device = 0
            transitions = defaultdict(int)
            
            for uid in completed_users:
                evts = sorted(user_events[uid], key=lambda e: e['timestamp'])
                
                device1 = None
                for event in evts:
                    if event['event_name'] == step1.get('event_name'):
                        if not step1.get('device_type') or event.get('device_type') == step1.get('device_type'):
                            device1 = event.get('device_type')
                            break
                
                device2 = None
                found_step1 = False
                for event in evts:
                    if not found_step1 and event['event_name'] == step1.get('event_name'):
                        found_step1 = True
                        continue
                    if found_step1 and event['event_name'] == step2.get('event_name'):
                        if not step2.get('device_type') or event.get('device_type') == step2.get('device_type'):
                            device2 = event.get('device_type')
                            break
                
                if device1 and device2:
                    transitions[(device1, device2)] += 1
                    if device1 == device2:
                        same_device += 1
                    else:
                        cross_device += 1
            
            total = same_device + cross_device
            transition_analysis.append({
                "from_step": step1.get('name', f'step_{i}'),
                "to_step": step2.get('name', f'step_{i+1}'),
                "same_device_count": same_device,
                "cross_device_count": cross_device,
                "total": total,
                "same_device_rate": round(same_device / total, 4) if total > 0 else None,
                "cross_device_rate": round(cross_device / total, 4) if total > 0 else None,
                "device_transitions": [
                    {
                        "from_device": d1,
                        "to_device": d2,
                        "count": count,
                        "percentage": round(count / total * 100, 2) if total > 0 else 0
                    }
                    for (d1, d2), count in sorted(transitions.items(), key=lambda x: -x[1])
                ]
            })

        return {
            "completed_users": len(completed_users),
            "step_transitions": transition_analysis
        }
