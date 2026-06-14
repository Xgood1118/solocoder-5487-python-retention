import os
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from modules.storage import MemoryStorage
from modules.event import EventModule
from modules.cohort import CohortModule
from modules.crossdevice import CrossDeviceModule
from modules.cohort_segment import SegmentModule
from modules.churn import ChurnModule

app = Flask(__name__)

storage = MemoryStorage()
event_module = EventModule()
cohort_module = CohortModule()
crossdevice_module = CrossDeviceModule()
segment_module = SegmentModule()
churn_module = ChurnModule()

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().timestamp(),
        "events_count": len(storage.events),
        "users_count": len(storage.user_profiles),
        "data_lag_hours": round(storage.get_data_lag_hours(), 2)
    })

@app.route('/api/events/track', methods=['POST'])
def track_events():
    try:
        data = request.get_json()
        if not data or 'events' not in data:
            return jsonify({"success": False, "error": "Missing 'events' in request body"}), 400
        
        result = event_module.track(data['events'])
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/events/query', methods=['GET', 'POST'])
def query_events():
    try:
        if request.method == 'POST':
            data = request.get_json() or {}
        else:
            data = request.args.to_dict()
        
        filters = data.get('filters')
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        limit = int(data.get('limit', 1000))
        offset = int(data.get('offset', 0))
        
        if start_time:
            start_time = float(start_time)
        if end_time:
            end_time = float(end_time)
        
        result = event_module.query(filters, start_time, end_time, limit, offset)
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/events/stats', methods=['GET'])
def event_stats():
    try:
        start_time = request.args.get('start_time', type=float)
        end_time = request.args.get('end_time', type=float)
        
        result = event_module.get_event_stats(start_time, end_time)
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/events/device-overlap', methods=['GET'])
def device_overlap():
    try:
        start_time = request.args.get('start_time', type=float)
        end_time = request.args.get('end_time', type=float)
        
        result = event_module.get_device_overlap(start_time, end_time)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/cohort/analyze', methods=['POST'])
def cohort_analyze():
    try:
        data = request.get_json() or {}
        
        granularity = data.get('granularity', 'day')
        periods = data.get('periods', [1, 3, 7, 14, 30])
        segment_by = data.get('segment_by')
        segment_values = data.get('segment_values')
        min_cohort_size = data.get('min_cohort_size', 10)
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if start_date:
            start_date = float(start_date)
        if end_date:
            end_date = float(end_date)
        
        result = cohort_module.analyze(
            granularity=granularity,
            periods=periods,
            segment_by=segment_by,
            segment_values=segment_values,
            min_cohort_size=min_cohort_size,
            start_date=start_date,
            end_date=end_date
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/cohort/compare', methods=['POST'])
def cohort_compare():
    try:
        data = request.get_json() or {}
        
        analysis_result = data.get('analysis_result')
        base_segment = data.get('base_segment')
        compare_segment = data.get('compare_segment')
        period = data.get('period', 7)
        
        if not analysis_result:
            return jsonify({"success": False, "error": "Missing 'analysis_result'"}), 400
        if not base_segment or not compare_segment:
            return jsonify({"success": False, "error": "Missing 'base_segment' or 'compare_segment'"}), 400
        
        result = cohort_module.compare_cohorts(
            analysis_result=analysis_result,
            base_segment=base_segment,
            compare_segment=compare_segment,
            period=period
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/crossdevice/timeline/<user_id>', methods=['GET'])
def crossdevice_timeline(user_id):
    try:
        start_time = request.args.get('start_time', type=float)
        end_time = request.args.get('end_time', type=float)
        
        result = crossdevice_module.get_user_timeline(user_id, start_time, end_time)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/crossdevice/switch-frequency', methods=['GET'])
def crossdevice_switch_frequency():
    try:
        start_time = request.args.get('start_time', type=float)
        end_time = request.args.get('end_time', type=float)
        min_events = request.args.get('min_events', 5, type=int)
        
        result = crossdevice_module.get_switch_frequency(start_time, end_time, min_events)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/crossdevice/duration', methods=['GET'])
def crossdevice_duration():
    try:
        start_time = request.args.get('start_time', type=float)
        end_time = request.args.get('end_time', type=float)
        session_timeout = request.args.get('session_timeout', 1800, type=int)
        
        result = crossdevice_module.get_duration_distribution(start_time, end_time, session_timeout)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/crossdevice/conversion-paths', methods=['GET', 'POST'])
def crossdevice_conversion_paths():
    try:
        if request.method == 'POST':
            data = request.get_json() or {}
        else:
            data = request.args.to_dict()
        
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        funnel_steps = data.get('funnel_steps')
        
        if start_time:
            start_time = float(start_time)
        if end_time:
            end_time = float(end_time)
        
        result = crossdevice_module.get_conversion_paths(start_time, end_time, funnel_steps)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/crossdevice/funnel', methods=['POST'])
def crossdevice_funnel():
    try:
        data = request.get_json() or {}
        
        funnel_definition = data.get('funnel')
        if not funnel_definition:
            return jsonify({"success": False, "error": "Missing 'funnel' definition"}), 400
        
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        require_sequence = data.get('require_sequence', True)
        
        if start_time:
            start_time = float(start_time)
        if end_time:
            end_time = float(end_time)
        
        result = crossdevice_module.analyze_funnel(funnel_definition, start_time, end_time, require_sequence)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/segments/validate', methods=['POST'])
def segment_validate():
    try:
        data = request.get_json() or {}
        expression = data.get('expression')
        
        if not expression:
            return jsonify({"success": False, "error": "Missing 'expression'"}), 400
        
        result = segment_module.validate_expression(expression)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/segments/preview', methods=['POST'])
def segment_preview():
    try:
        data = request.get_json() or {}
        expression = data.get('expression')
        limit = data.get('limit', 50)
        
        if not expression:
            return jsonify({"success": False, "error": "Missing 'expression'"}), 400
        
        result = segment_module.preview_segment(expression, limit)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/segments', methods=['GET', 'POST'])
def segments():
    try:
        if request.method == 'POST':
            data = request.get_json() or {}
            name = data.get('name')
            expression = data.get('expression')
            description = data.get('description')
            subscribers = data.get('subscribers', [])
            
            if not name or not expression:
                return jsonify({"success": False, "error": "Missing 'name' or 'expression'"}), 400
            
            result = segment_module.create_segment(name, expression, description, subscribers)
            return jsonify(result)
        else:
            result = segment_module.list_segments()
            return jsonify({"success": True, "segments": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/segments/<segment_id>', methods=['GET', 'DELETE'])
def segment_detail(segment_id):
    try:
        if request.method == 'DELETE':
            result = segment_module.delete_segment(segment_id)
            return jsonify(result)
        else:
            segment = storage.get_segment(segment_id)
            if not segment:
                return jsonify({"success": False, "error": "Segment not found"}), 404
            
            members = segment_module.get_segment_members(segment_id)
            return jsonify({
                "success": True,
                "segment": segment,
                "member_count": len(members),
                "members": members[:100]
            })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/segments/<segment_id>/members', methods=['GET'])
def segment_members(segment_id):
    try:
        limit = request.args.get('limit', 100, type=int)
        members = segment_module.get_segment_members(segment_id)
        
        return jsonify({
            "success": True,
            "segment_id": segment_id,
            "member_count": len(members),
            "members": members[:limit]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/segments/compare', methods=['POST'])
def segments_compare():
    try:
        data = request.get_json() or {}
        segment_ids = data.get('segment_ids')
        metrics = data.get('metrics')
        
        if not segment_ids or len(segment_ids) < 2:
            return jsonify({"success": False, "error": "Need at least 2 segment_ids to compare"}), 400
        
        result = segment_module.compare_segments(segment_ids, metrics)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/churn/rules', methods=['GET', 'POST'])
def churn_rules():
    try:
        if request.method == 'POST':
            data = request.get_json() or {}
            name = data.get('name')
            conditions = data.get('conditions')
            description = data.get('description')
            
            if not name or not conditions:
                return jsonify({"success": False, "error": "Missing 'name' or 'conditions'"}), 400
            
            result = churn_module.create_rule(name, conditions, description)
            return jsonify(result)
        else:
            result = churn_module.get_rules()
            return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/churn/run/<rule_id>', methods=['POST'])
def churn_run(rule_id):
    try:
        data = request.get_json() or {}
        check_data_integrity = data.get('check_data_integrity', True)
        data_lag_threshold_hours = data.get('data_lag_threshold_hours', 2)
        now = data.get('now')
        
        result = churn_module.run_churn_detection(
            rule_id=rule_id,
            check_data_integrity=check_data_integrity,
            data_lag_threshold_hours=data_lag_threshold_hours,
            now=now
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/churn/results', methods=['GET'])
def churn_results():
    try:
        rule_id = request.args.get('rule_id')
        limit = request.args.get('limit', 100, type=int)
        
        result = churn_module.get_churn_results(rule_id, limit)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/churn/reach', methods=['POST'])
def churn_reach():
    try:
        data = request.get_json() or {}
        rule_id = data.get('rule_id')
        user_ids = data.get('user_ids')
        channel = data.get('channel', 'sms')
        content = data.get('content')
        
        if not rule_id or not user_ids:
            return jsonify({"success": False, "error": "Missing 'rule_id' or 'user_ids'"}), 400
        
        result = churn_module.record_reach(rule_id, user_ids, channel, content)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/churn/evaluate-recall', methods=['POST'])
def churn_evaluate_recall():
    try:
        data = request.get_json() or {}
        rule_id = data.get('rule_id')
        force_eval = data.get('force_eval', False)
        now = data.get('now')
        
        result = churn_module.evaluate_recall(rule_id, now=now, force_eval=force_eval)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/churn/reach-history', methods=['GET'])
def churn_reach_history():
    try:
        rule_id = request.args.get('rule_id')
        user_id = request.args.get('user_id')
        
        result = churn_module.get_reach_history(rule_id, user_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/churn/data-integrity', methods=['GET'])
def churn_data_integrity():
    try:
        result = churn_module.get_data_integrity_status()
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

def scheduled_churn_detection():
    print(f"[{datetime.now()}] Starting scheduled churn detection...")
    
    integrity = churn_module.get_data_integrity_status()
    if not integrity.get('is_data_complete_for_churn'):
        print(f"[{datetime.now()}] Data integrity check failed. Lag: {integrity.get('data_lag_hours')}h. Skipping.")
        return
    
    rules = storage.get_all_churn_rules()
    for rule in rules:
        if rule.get('enabled', True):
            print(f"[{datetime.now()}] Running churn detection for rule: {rule.get('name')}")
            result = churn_module.run_churn_detection(
                rule_id=rule['rule_id'],
                check_data_integrity=True
            )
            print(f"[{datetime.now()}] Rule {rule.get('name')}: found {result.get('churn_users_found', 0)} churn users")

def scheduled_snapshot():
    print(f"[{datetime.now()}] Saving periodic snapshot...")
    storage.save_snapshot()
    print(f"[{datetime.now()}] Snapshot saved")

def scheduled_segment_check():
    print(f"[{datetime.now()}] Checking segment changes...")
    segments = storage.get_all_segments()
    for segment in segments:
        if segment.get('subscribers'):
            result = segment_module.check_and_notify_subscribers(segment['segment_id'])
            if result.get('changed'):
                print(f"[{datetime.now()}] Segment {segment.get('name')} changed: +{len(result.get('added', []))} -{len(result.get('removed', []))}")

def generate_test_events():
    now = datetime.now()
    test_events = []
    
    channels = ['promotion', 'ad', 'invite', 'natural']
    devices = ['ios', 'android', 'web', 'mp']
    product_lines = ['app', 'web', 'mp']
    
    num_users = 200
    num_weeks = 10
    users_per_week = num_users // num_weeks
    
    for user_idx in range(num_users):
        user_id = f"user_{user_idx:03d}"
        week_idx = user_idx // users_per_week
        day_in_week = user_idx % users_per_week
        
        channel = channels[user_idx % 4]
        first_device = devices[user_idx % 4]
        first_product_line = product_lines[user_idx % 3]
        user_level = 'vip' if user_idx % 5 == 0 else 'normal'
        
        first_active = now - timedelta(days=(num_weeks - week_idx) * 7 + day_in_week % 5)
        
        base_props = {
            "register_channel": channel,
            "user_level": user_level,
            "session_id": f"sess_{user_idx}"
        }
        
        test_events.append({
            "event_name": "app_open",
            "timestamp": first_active.timestamp(),
            "user_id": user_id,
            "device_type": first_device,
            "product_line": first_product_line,
            "properties": {**base_props, "launch_type": "cold"}
        })
        
        test_events.append({
            "event_name": "page_view",
            "timestamp": first_active.timestamp() + 60,
            "user_id": user_id,
            "device_type": first_device,
            "product_line": first_product_line,
            "properties": {**base_props, "page": "home"}
        })
        
        if user_idx % 3 == 0:
            test_events.append({
                "event_name": "register",
                "timestamp": first_active.timestamp() + 120,
                "user_id": user_id,
                "device_type": first_device,
                "product_line": first_product_line,
                "properties": {**base_props, "channel": channel}
            })
        
        max_active_days = min((num_weeks - week_idx) * 7, 60)
        retention_pattern = user_idx % 5
        active_days = []
        
        if retention_pattern == 0:
            active_days = list(range(1, min(max_active_days, 45)))
        elif retention_pattern == 1:
            active_days = [d for d in [1, 3, 7, 14, 21, 30] if d < max_active_days]
        elif retention_pattern == 2:
            active_days = [d for d in [1, 3, 7, 14] if d < max_active_days]
        elif retention_pattern == 3:
            active_days = [d for d in [1, 7, 30] if d < max_active_days]
        else:
            active_days = [1] if max_active_days > 1 else []
        
        if user_idx >= num_users - 30:
            active_days = [d for d in active_days if d < 18]
        
        for day_offset in active_days:
            active_time = first_active + timedelta(days=day_offset, hours=user_idx % 12)
            
            use_web = user_idx % 4 == 0 and day_offset > 7
            use_mp = user_idx % 5 == 0 and day_offset > 14
            
            if use_web:
                device = 'web'
                product = 'web'
            elif use_mp:
                device = 'mp'
                product = 'mp'
            else:
                device = first_device
                product = first_product_line
            
            test_events.append({
                "event_name": "login",
                "timestamp": active_time.timestamp(),
                "user_id": user_id,
                "device_type": device,
                "product_line": product,
                "properties": {**base_props, "login_method": "password"}
            })
            
            test_events.append({
                "event_name": "page_view",
                "timestamp": active_time.timestamp() + 30,
                "user_id": user_id,
                "device_type": device,
                "product_line": product,
                "properties": {**base_props, "page": "product_list"}
            })
            
            test_events.append({
                "event_name": "page_view",
                "timestamp": active_time.timestamp() + 60,
                "user_id": user_id,
                "device_type": device,
                "product_line": product,
                "properties": {**base_props, "page": f"product_detail_{user_idx}"}
            })
            
            if day_offset % 7 == 0:
                test_events.append({
                    "event_name": "search",
                    "timestamp": active_time.timestamp() + 90,
                    "user_id": user_id,
                    "device_type": device,
                    "product_line": product,
                    "properties": {
                        **base_props,
                        "keyword": "退款" if user_idx % 17 == 0 and day_offset > 30 else f"商品_{user_idx}_{day_offset}"
                    }
                })
            
            if day_offset % 10 == 0 and user_idx % 2 == 0:
                test_events.append({
                    "event_name": "add_to_cart",
                    "timestamp": active_time.timestamp() + 120,
                    "user_id": user_id,
                    "device_type": device,
                    "product_line": product,
                    "properties": {**base_props, "product_id": f"prod_{user_idx}", "quantity": 1, "price": 99.0 + user_idx}
                })
                
                if day_offset % 15 == 0:
                    other_device = 'web' if device != 'web' else 'ios'
                    other_product = 'web' if product != 'web' else 'app'
                    
                    test_events.append({
                        "event_name": "order_created",
                        "timestamp": active_time.timestamp() + 3600,
                        "user_id": user_id,
                        "device_type": other_device,
                        "product_line": other_product,
                        "properties": {**base_props, "order_id": f"order_{user_idx}_{day_offset}", "amount": 99.0 + user_idx}
                    })
                    
                    test_events.append({
                        "event_name": "order_completed",
                        "timestamp": active_time.timestamp() + 3660,
                        "user_id": user_id,
                        "device_type": other_device,
                        "product_line": other_product,
                        "properties": {**base_props, "order_id": f"order_{user_idx}_{day_offset}", "amount": 99.0 + user_idx, "payment_method": "alipay"}
                    })
        
        if user_idx % 7 == 0:
            churn_time = first_active + timedelta(days=20)
            test_events.append({
                "event_name": "search",
                "timestamp": churn_time.timestamp(),
                "user_id": user_id,
                "device_type": first_device,
                "product_line": first_product_line,
                "properties": {**base_props, "keyword": "怎么注销账号"}
            })
            
            test_events.append({
                "event_name": "search",
                "timestamp": churn_time.timestamp() + 60,
                "user_id": user_id,
                "device_type": first_device,
                "product_line": first_product_line,
                "properties": {**base_props, "keyword": "申请退款"}
            })
    
    print(f"Generated {len(test_events)} test events")
    return test_events

def init_test_data():
    print("Initializing test data...")
    
    if len(storage.events) > 0:
        print(f"Data already exists ({len(storage.events)} events), skipping test data initialization")
        return
    
    test_events = generate_test_events()
    result = event_module.track(test_events)
    
    print(f"Test data initialization complete: {result.get('stored', 0)} events stored")
    
    default_churn_rule = {
        "name": "标准流失规则",
        "conditions": [
            {"type": "no_activity", "days": 14},
            {"type": "no_purchase", "days": 30}
        ],
        "description": "过去14天无活跃且过去30天无消费的用户"
    }
    churn_module.create_rule(
        name=default_churn_rule["name"],
        conditions=default_churn_rule["conditions"],
        description=default_churn_rule["description"]
    )
    print("Default churn rule created")
    
    segment_expression = "past 30 days in 'ios' event_count 'page_view' >= 5 AND past 30 days in 'web' event_count 'order_completed' >= 1"
    segment_module.create_segment(
        name="跨端高价值用户",
        expression=segment_expression,
        description="iOS端活跃且Web端有订单的用户",
        subscribers=["ops@example.com"]
    )
    print("Default segment created")

def run_cohort_demo():
    print("\n" + "=" * 80)
    print("  COHORT RETENTION ANALYSIS DEMO")
    print("=" * 80)
    
    result = cohort_module.analyze(
        granularity='week',
        periods=[1, 3, 7, 14, 30],
        min_cohort_size=5
    )
    
    if not result.get('success'):
        print(f"  Cohort analysis failed: {result.get('error')}")
        return
    
    print(f"  Granularity: {result.get('granularity')}")
    print(f"  Periods: {result.get('periods')}")
    print(f"  Total cohorts: {result.get('total_cohorts')}")
    print(f"  Filtered small cohorts (size < {result.get('min_cohort_size')}): {result.get('filtered_small_cohorts')}")
    print(f"\n  Retention Matrix:")
    
    header = f"  {'Cohort':<25} {'Users':<8}"
    for p in result.get('periods', []):
        header += f" {'W'+str(p) if result.get('granularity')=='week' else 'D'+str(p):<14}"
    print(header)
    print("  " + "-" * len(header))
    
    for row in result.get('matrix', []):
        line = f"  {row['cohort_label']:<25} {row['user_count']:<8}"
        periods_data = {p['period_days']: p for p in row['periods']}
        for p in result.get('periods', []):
            pd = periods_data.get(p)
            if pd:
                rate = pd['retention_rate']
                ci = pd.get('confidence_interval')
                if ci and pd.get('small_sample'):
                    line += f" {rate:.1%}±{ci['margin']:.1%}  "
                else:
                    line += f" {rate:.1%}          "
            else:
                line += f" {'N/A':<14}"
        print(line)
    
    print(f"\n  Device coverage: ios, web, mp events present")
    stats = event_module.get_event_stats()
    by_device = stats.get('by_device', {})
    for device in ['ios', 'android', 'web', 'mp']:
        count = by_device.get(device, 0)
        if count:
            print(f"    {device}: {count} events")
    
    overlap = event_module.get_device_overlap()
    print(f"\n  Cross-device users: {overlap.get('multi_device_users')} out of {overlap.get('total_users')}")
    print(f"  Single-device users: {overlap.get('single_device_users')}")
    
    print("=" * 80 + "\n")

def create_app():
    scheduler = BackgroundScheduler()
    
    scheduler.add_job(
        scheduled_churn_detection,
        CronTrigger(hour=2, minute=0),
        id='churn_detection_daily',
        replace_existing=True
    )
    
    scheduler.add_job(
        scheduled_snapshot,
        CronTrigger(minute='*/5'),
        id='snapshot_periodic',
        replace_existing=True
    )
    
    scheduler.add_job(
        scheduled_segment_check,
        CronTrigger(hour='*/6'),
        id='segment_check',
        replace_existing=True
    )
    
    scheduler.start()
    print("Scheduler started")
    
    init_test_data()
    run_cohort_demo()
    
    return app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app = create_app()
    
    print(f"Starting server on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False)
