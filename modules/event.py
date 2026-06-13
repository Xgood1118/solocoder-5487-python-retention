from datetime import datetime
from typing import List, Dict, Any, Optional
from .storage import MemoryStorage

VALID_DEVICE_TYPES = {'ios', 'android', 'web', 'mp', 'wx'}
VALID_PRODUCT_LINES = {'app', 'web', 'mp', 'wx', 'official'}
REQUIRED_FIELDS = {'event_name', 'timestamp', 'user_id', 'device_type', 'product_line'}

class EventModule:
    def __init__(self):
        self.storage = MemoryStorage()

    def validate_event(self, event: Dict[str, Any]) -> Optional[str]:
        for field in REQUIRED_FIELDS:
            if field not in event:
                return f"Missing required field: {field}"
        
        if event['device_type'] not in VALID_DEVICE_TYPES:
            return f"Invalid device_type: {event['device_type']}. Must be one of {VALID_DEVICE_TYPES}"
        
        if event['product_line'] not in VALID_PRODUCT_LINES:
            return f"Invalid product_line: {event['product_line']}. Must be one of {VALID_PRODUCT_LINES}"
        
        if not isinstance(event['timestamp'], (int, float)):
            return f"Invalid timestamp: must be a number (unix timestamp)"
        
        if not isinstance(event['user_id'], str) or not event['user_id'].strip():
            return "Invalid user_id: must be a non-empty string"
        
        if 'properties' in event and not isinstance(event['properties'], dict):
            return "Invalid properties: must be a dict"
        
        return None

    def track(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(events, list):
            return {"success": False, "error": "Events must be a list", "received": 0, "stored": 0}
        
        valid_events = []
        errors = []
        
        for idx, event in enumerate(events):
            error = self.validate_event(event)
            if error:
                errors.append({"index": idx, "error": error, "event": event})
            else:
                event_copy = event.copy()
                if 'properties' not in event_copy:
                    event_copy['properties'] = {}
                valid_events.append(event_copy)
        
        event_ids = []
        if valid_events:
            event_ids = self.storage.add_events(valid_events)
        
        return {
            "success": True,
            "received": len(events),
            "stored": len(valid_events),
            "failed": len(errors),
            "event_ids": event_ids,
            "errors": errors
        }

    def query(self, filters: Dict[str, Any] = None, 
              start_time: float = None, end_time: float = None,
              limit: int = 1000, offset: int = 0) -> Dict[str, Any]:
        events = self.storage.get_events(filters)
        
        if start_time is not None:
            events = [e for e in events if e['timestamp'] >= start_time]
        if end_time is not None:
            events = [e for e in events if e['timestamp'] <= end_time]
        
        total = len(events)
        events = events[offset:offset + limit]
        
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "events": events
        }

    def get_user_events(self, user_id: str, 
                        start_time: float = None, end_time: float = None,
                        event_names: List[str] = None) -> List[Dict[str, Any]]:
        filters = {"user_id": user_id}
        if event_names:
            filters["event_name"] = event_names
        events = self.storage.get_events(filters)
        
        if start_time is not None:
            events = [e for e in events if e['timestamp'] >= start_time]
        if end_time is not None:
            events = [e for e in events if e['timestamp'] <= end_time]
        
        return events

    def get_event_stats(self, start_time: float = None, end_time: float = None) -> Dict[str, Any]:
        events = self.storage.get_events()
        
        if start_time is not None:
            events = [e for e in events if e['timestamp'] >= start_time]
        if end_time is not None:
            events = [e for e in events if e['timestamp'] <= end_time]
        
        stats = {
            "total_events": len(events),
            "unique_users": len(set(e['user_id'] for e in events)),
            "by_device": {},
            "by_product_line": {},
            "by_event_name": {}
        }
        
        for e in events:
            stats["by_device"][e['device_type']] = stats["by_device"].get(e['device_type'], 0) + 1
            stats["by_product_line"][e['product_line']] = stats["by_product_line"].get(e['product_line'], 0) + 1
            stats["by_event_name"][e['event_name']] = stats["by_event_name"].get(e['event_name'], 0) + 1
        
        return stats

    def get_device_overlap(self, start_time: float = None, end_time: float = None) -> Dict[str, Any]:
        events = self.storage.get_events()
        
        if start_time is not None:
            events = [e for e in events if e['timestamp'] >= start_time]
        if end_time is not None:
            events = [e for e in events if e['timestamp'] <= end_time]
        
        user_devices: Dict[str, set] = {}
        for e in events:
            if e['user_id'] not in user_devices:
                user_devices[e['user_id']] = set()
            user_devices[e['user_id']].add(e['device_type'])
        
        device_counts = {}
        for user, devices in user_devices.items():
            count = len(devices)
            device_counts[count] = device_counts.get(count, 0) + 1
        
        device_pairs = {}
        for user, devices in user_devices.items():
            devices_list = sorted(list(devices))
            for i in range(len(devices_list)):
                for j in range(i + 1, len(devices_list)):
                    pair = f"{devices_list[i]}+{devices_list[j]}"
                    device_pairs[pair] = device_pairs.get(pair, 0) + 1
        
        return {
            "success": True,
            "total_users": len(user_devices),
            "device_count_distribution": device_counts,
            "device_overlap_pairs": device_pairs,
            "single_device_users": device_counts.get(1, 0),
            "multi_device_users": sum(v for k, v in device_counts.items() if k > 1)
        }
