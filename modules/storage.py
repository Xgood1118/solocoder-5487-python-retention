import json
import os
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')

class MemoryStorage:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self.events: List[Dict[str, Any]] = []
        self.user_profiles: Dict[str, Dict[str, Any]] = {}
        self.segments: Dict[str, Dict[str, Any]] = {}
        self.churn_rules: Dict[str, Dict[str, Any]] = {}
        self.churn_results: List[Dict[str, Any]] = []
        self.reach_history: List[Dict[str, Any]] = []
        self.snapshot_interval = 300
        self.last_event_timestamp: Optional[float] = None
        self._load_from_snapshot()

    def _snapshot_path(self, name: str) -> str:
        return os.path.join(DATA_DIR, f'{name}.json')

    def _load_from_snapshot(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        for name in ['events', 'user_profiles', 'segments', 'churn_rules', 'churn_results', 'reach_history']:
            path = self._snapshot_path(name)
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        setattr(self, name, data)
                except Exception as e:
                    print(f"Warning: Failed to load {name} snapshot: {e}")
        if self.events:
            self.last_event_timestamp = max(e['timestamp'] for e in self.events)

    def save_snapshot(self, name: str = None):
        os.makedirs(DATA_DIR, exist_ok=True)
        items = [name] if name else ['events', 'user_profiles', 'segments', 'churn_rules', 'churn_results', 'reach_history']
        for item in items:
            path = self._snapshot_path(item)
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(getattr(self, item), f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"Warning: Failed to save {item} snapshot: {e}")

    def add_events(self, events: List[Dict[str, Any]]) -> List[str]:
        with self._lock:
            event_ids = []
            for event in events:
                event_id = f"evt_{datetime.now().timestamp()}_{len(self.events)}"
                event['event_id'] = event_id
                event['received_at'] = datetime.now().timestamp()
                self.events.append(event)
                event_ids.append(event_id)
                self._update_user_profile(event)
                if self.last_event_timestamp is None or event['timestamp'] > self.last_event_timestamp:
                    self.last_event_timestamp = event['timestamp']
            self.save_snapshot('events')
            self.save_snapshot('user_profiles')
            return event_ids

    def _update_user_profile(self, event: Dict[str, Any]):
        user_id = event['user_id']
        if user_id not in self.user_profiles:
            self.user_profiles[user_id] = {
                'user_id': user_id,
                'first_active': event['timestamp'],
                'first_device': event.get('device_type'),
                'first_product_line': event.get('product_line'),
                'register_channel': event.get('properties', {}).get('register_channel', 'natural'),
                'user_level': event.get('properties', {}).get('user_level', 'normal'),
                'devices': [],
                'product_lines': [],
                'last_active': event['timestamp'],
                'total_events': 0,
                'total_spent': 0.0,
                'order_count': 0
            }
        profile = self.user_profiles[user_id]
        
        device = event.get('device_type')
        if device and device not in profile['devices']:
            profile['devices'].append(device)
        pl = event.get('product_line')
        if pl and pl not in profile['product_lines']:
            profile['product_lines'].append(pl)
        if event['timestamp'] > profile['last_active']:
            profile['last_active'] = event['timestamp']
        profile['total_events'] += 1
        
        if event.get('event_name') == 'order_completed':
            profile['total_spent'] += float(event.get('properties', {}).get('amount', 0))
            profile['order_count'] += 1

    def get_events(self, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        events = self.events.copy()
        if filters:
            for key, value in filters.items():
                if callable(value):
                    events = [e for e in events if value(e.get(key))]
                elif isinstance(value, list):
                    events = [e for e in events if e.get(key) in value]
                else:
                    events = [e for e in events if e.get(key) == value]
        return sorted(events, key=lambda e: e['timestamp'])

    def get_users(self, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        users = list(self.user_profiles.values())
        if filters:
            for key, value in filters.items():
                if callable(value):
                    users = [u for u in users if value(u.get(key))]
                elif isinstance(value, list):
                    users = [u for u in users if u.get(key) in value]
                else:
                    users = [u for u in users if u.get(key) == value]
        return users

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self.user_profiles.get(user_id)

    def save_segment(self, segment: Dict[str, Any]) -> str:
        with self._lock:
            if 'segment_id' not in segment:
                segment['segment_id'] = f"seg_{datetime.now().timestamp()}"
            segment['created_at'] = datetime.now().timestamp()
            self.segments[segment['segment_id']] = segment
            self.save_snapshot('segments')
            return segment['segment_id']

    def get_segment(self, segment_id: str) -> Optional[Dict[str, Any]]:
        return self.segments.get(segment_id)

    def get_all_segments(self) -> List[Dict[str, Any]]:
        return list(self.segments.values())

    def delete_segment(self, segment_id: str) -> bool:
        with self._lock:
            if segment_id in self.segments:
                del self.segments[segment_id]
                self.save_snapshot('segments')
                return True
            return False

    def save_churn_rule(self, rule: Dict[str, Any]) -> str:
        with self._lock:
            if 'rule_id' not in rule:
                rule['rule_id'] = f"rule_{datetime.now().timestamp()}"
            rule['created_at'] = datetime.now().timestamp()
            rule['enabled'] = rule.get('enabled', True)
            self.churn_rules[rule['rule_id']] = rule
            self.save_snapshot('churn_rules')
            return rule['rule_id']

    def get_churn_rule(self, rule_id: str) -> Optional[Dict[str, Any]]:
        return self.churn_rules.get(rule_id)

    def get_all_churn_rules(self) -> List[Dict[str, Any]]:
        return list(self.churn_rules.values())

    def save_churn_results(self, results: List[Dict[str, Any]]):
        with self._lock:
            self.churn_results.extend(results)
            self.save_snapshot('churn_results')

    def get_churn_results(self, rule_id: str = None) -> List[Dict[str, Any]]:
        results = self.churn_results
        if rule_id:
            results = [r for r in results if r.get('rule_id') == rule_id]
        return sorted(results, key=lambda r: r['run_time'], reverse=True)

    def add_reach_history(self, records: List[Dict[str, Any]]):
        with self._lock:
            self.reach_history.extend(records)
            self.save_snapshot('reach_history')

    def get_reach_history(self, user_id: str = None, rule_id: str = None) -> List[Dict[str, Any]]:
        history = self.reach_history
        if user_id:
            history = [h for h in history if h.get('user_id') == user_id]
        if rule_id:
            history = [h for h in history if h.get('rule_id') == rule_id]
        return history

    def is_data_complete(self, hours: int = 2) -> bool:
        if self.last_event_timestamp is None:
            return False
        now = datetime.now().timestamp()
        if self.last_event_timestamp > now:
            return True
        cutoff = now - hours * 3600
        return self.last_event_timestamp >= cutoff

    def get_data_lag_hours(self) -> float:
        if self.last_event_timestamp is None:
            return float('inf')
        now = datetime.now().timestamp()
        if self.last_event_timestamp > now:
            return 0.0
        return (now - self.last_event_timestamp) / 3600

    def get_effective_now(self) -> float:
        if self.last_event_timestamp is None:
            return datetime.now().timestamp()
        return max(self.last_event_timestamp, datetime.now().timestamp())
