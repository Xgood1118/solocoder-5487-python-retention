import sys
import json
import urllib.request
import urllib.error
from datetime import datetime

BASE_URL = "http://127.0.0.1:5000"

def api_get(path, params=None):
    url = BASE_URL + path
    if params:
        url += "?" + "&".join([f"{k}={v}" for k, v in params.items()])
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()}"}
    except Exception as e:
        return {"error": str(e)}

def api_post(path, data=None):
    url = BASE_URL + path
    req = urllib.request.Request(
        url,
        data=json.dumps(data or {}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()}"}
    except Exception as e:
        return {"error": str(e)}

def print_separator(title=""):
    print(f"\n{'='*80}")
    if title:
        print(f"  {title}")
        print("="*80)

def test_health():
    print_separator("1. HEALTH CHECK")
    result = api_get("/health")
    print(f"  Status: {result.get('status')}")
    print(f"  Events: {result.get('events_count')}")
    print(f"  Users: {result.get('users_count')}")
    print(f"  Data lag: {result.get('data_lag_hours')}h")
    return result.get('status') == 'ok'

def test_event_stats():
    print_separator("2. EVENT STATISTICS")
    result = api_get("/api/events/stats")
    print(f"  Total events: {result.get('total_events')}")
    print(f"  Unique users: {result.get('unique_users')}")
    print(f"  By device: {json.dumps(result.get('by_device'), indent=2, ensure_ascii=False)}")
    print(f"  By product line: {json.dumps(result.get('by_product_line'), indent=2, ensure_ascii=False)}")
    return result.get('success')

def test_device_overlap():
    print_separator("3. DEVICE OVERLAP")
    result = api_get("/api/events/device-overlap")
    print(f"  Total users: {result.get('total_users')}")
    print(f"  Single device users: {result.get('single_device_users')}")
    print(f"  Multi device users: {result.get('multi_device_users')}")
    print(f"  Device count distribution: {result.get('device_count_distribution')}")
    print(f"  Device overlap pairs: {result.get('device_overlap_pairs')}")
    return result.get('success')

def test_cohort_analyze():
    print_separator("4. COHORT ANALYSIS - RETENTION MATRIX")
    
    print("  --- Basic cohort (by day) ---")
    result = api_post("/api/cohort/analyze", {
        "granularity": "day",
        "periods": [1, 3, 7, 14, 30],
        "min_cohort_size": 1
    })
    
    if result.get('success'):
        print(f"  Granularity: {result.get('granularity')}")
        print(f"  Periods: {result.get('periods')}")
        print(f"  Total cohorts: {result.get('total_cohorts')}")
        print(f"  Filtered small cohorts: {result.get('filtered_small_cohorts')}")
        print(f"  Min cohort size: {result.get('min_cohort_size')}")
        print(f"\n  Retention Matrix (first 5 cohorts):")
        print(f"  {'Cohort':<15} {'Users':<8} {'D1':<10} {'D3':<10} {'D7':<10} {'D14':<10} {'D30':<10}")
        print("  " + "-"*80)
        
        for row in result.get('matrix', [])[:5]:
            cohort_label = row['cohort_label']
            user_count = row['user_count']
            periods_data = {p['period_days']: p for p in row['periods']}
            
            d1 = f"{periods_data[1]['retention_rate']:.1%}±{periods_data[1]['confidence_interval']['margin']:.1%}" if periods_data[1]['confidence_interval'] else f"{periods_data[1]['retention_rate']:.1%}"
            d3 = f"{periods_data[3]['retention_rate']:.1%}±{periods_data[3]['confidence_interval']['margin']:.1%}" if periods_data[3]['confidence_interval'] else f"{periods_data[3]['retention_rate']:.1%}"
            d7 = f"{periods_data[7]['retention_rate']:.1%}±{periods_data[7]['confidence_interval']['margin']:.1%}" if periods_data[7]['confidence_interval'] else f"{periods_data[7]['retention_rate']:.1%}"
            d14 = f"{periods_data[14]['retention_rate']:.1%}±{periods_data[14]['confidence_interval']['margin']:.1%}" if periods_data[14]['confidence_interval'] else f"{periods_data[14]['retention_rate']:.1%}"
            d30 = f"{periods_data[30]['retention_rate']:.1%}±{periods_data[30]['confidence_interval']['margin']:.1%}" if periods_data[30]['confidence_interval'] else f"{periods_data[30]['retention_rate']:.1%}"
            
            print(f"  {cohort_label:<15} {user_count:<8} {d1:<10} {d3:<10} {d7:<10} {d14:<10} {d30:<10}")
    
    print("\n  --- Segmented cohort by register channel ---")
    result2 = api_post("/api/cohort/analyze", {
        "granularity": "day",
        "periods": [7, 30],
        "segment_by": "register_channel",
        "min_cohort_size": 1
    })
    
    if result2.get('success'):
        print(f"  Segment by: {result2.get('segment_by')}")
        print(f"  Total cohorts: {result2.get('total_cohorts')}")
        print(f"\n  Segmented Retention (D7):")
        print(f"  {'Cohort':<15} {'Segment':<12} {'Users':<8} {'D7 Retention':<15}")
        print("  " + "-"*60)
        
        for row in result2.get('matrix', [])[:8]:
            cohort_label = row['cohort_label']
            segment = row['segment']
            user_count = row['user_count']
            d7 = next((p['retention_rate'] for p in row['periods'] if p['period_days'] == 7), None)
            print(f"  {cohort_label:<15} {segment:<12} {user_count:<8} {d7:.1%}" if d7 else f"  {cohort_label:<15} {segment:<12} {user_count:<8} N/A")
    
    print("\n  --- Cohort comparison ---")
    compare_result = api_post("/api/cohort/compare", {
        "analysis_result": result2,
        "base_segment": "ad",
        "compare_segment": "invite",
        "period": 7
    })
    
    if compare_result.get('success'):
        print(f"\n  Comparing: {compare_result.get('base_segment')} vs {compare_result.get('compare_segment')}")
        print(f"  Period: D{compare_result.get('period_days')}")
        print(f"\n  Conclusions:")
        for conclusion in compare_result.get('conclusions', []):
            print(f"    - {conclusion}")
    
    return result.get('success') and result2.get('success')

def test_crossdevice_timeline():
    print_separator("5. CROSS-DEVICE USER TIMELINE")
    
    users_result = api_get("/api/events/stats")
    test_user_id = "user_000"
    
    result = api_get(f"/api/crossdevice/timeline/{test_user_id}")
    if result.get('success'):
        print(f"  User: {result.get('user_id')}")
        print(f"  Devices used: {result.get('user_profile', {}).get('devices')}")
        print(f"  Total events: {result.get('total_events')}")
        print(f"  Device switches: {result.get('device_switches')}")
        print(f"  Device colors: {result.get('device_colors')}")
        
        print(f"\n  Timeline (first 10 events):")
        for event in result.get('timeline', [])[:10]:
            print(f"    [{event['datetime']}] {event['device_type']:<8} {event['event_name']:<20} color={event['color']}")
        
        if result.get('switch_points'):
            print(f"\n  Switch points:")
            for sp in result.get('switch_points', [])[:5]:
                print(f"    [{sp['index']}] {sp['from_device']} -> {sp['to_device']}")
    
    return result.get('success')

def test_crossdevice_switch_frequency():
    print_separator("6. CROSS-DEVICE SWITCH FREQUENCY")
    
    result = api_get("/api/crossdevice/switch-frequency", {"min_events": 3})
    if result.get('success'):
        print(f"  Total users: {result.get('total_users')}")
        print(f"  Observation: {result.get('observation')}")
        print(f"  Single device: {result.get('single_device_users_pct')}%")
        print(f"  Multi device: {result.get('multi_device_users_pct')}%")
        print(f"  Avg switches per user: {result.get('avg_switches_per_user')}")
        print(f"  Max switches: {result.get('max_switches')}")
        print(f"  Distribution: {json.dumps(result.get('switch_count_distribution'), ensure_ascii=False)}")
        print(f"  Percentiles: {json.dumps(result.get('percentiles'), ensure_ascii=False)}")
    
    return result.get('success')

def test_crossdevice_duration():
    print_separator("7. CROSS-DEVICE DURATION DISTRIBUTION")
    
    result = api_get("/api/crossdevice/duration")
    if result.get('success'):
        print(f"  Session timeout: {result.get('session_timeout_seconds')}s")
        print(f"\n  By device:")
        for device, data in result.get('by_device', {}).items():
            print(f"    {device:<8}: sessions={data['total_sessions']:<5} total={data['total_minutes']:<10}min avg={data['avg_session_minutes']:<8}min median={data['median_session_minutes']:<8}min")
    
    return result.get('success')

def test_crossdevice_conversion_paths():
    print_separator("8. CROSS-DEVICE CONVERSION PATHS")
    
    result = api_post("/api/crossdevice/conversion-paths")
    if result.get('success'):
        print(f"  Funnel steps: {result.get('funnel_steps')}")
        print(f"  Total paths: {result.get('total_paths')}")
        print(f"  Cross-device paths: {result.get('cross_device_paths')}")
        print(f"  Same-device paths: {result.get('same_device_paths')}")
        
        if result.get('path_summary'):
            print(f"\n  Top paths:")
            for path in result.get('path_summary', [])[:5]:
                path_str = " -> ".join([f"{s[0]}({s[1]})" for s in path['path']])
                print(f"    [{path['count']} users] {path_str}")
                print(f"      Cross-device: {path['cross_device']}, {path['percentage']}%")
        
        if result.get('device_transitions'):
            print(f"\n  Device transitions:")
            for trans in result.get('device_transitions', [])[:5]:
                print(f"    {trans['from_step']}:{trans['from_device']} -> {trans['to_step']}:{trans['to_device']} = {trans['count']} (cross={trans['cross_device']})")
    
    return result.get('success')

def test_crossdevice_funnel():
    print_separator("9. CROSS-DEVICE FUNNEL ANALYSIS")
    
    funnel_def = [
        {"name": "APP加购", "event_name": "add_to_cart", "device_type": "ios"},
        {"name": "Web结算", "event_name": "order_completed", "device_type": "web"}
    ]
    
    result = api_post("/api/crossdevice/funnel", {"funnel": funnel_def})
    if result.get('success'):
        print(f"  Total users at start: {result.get('total_users')}")
        print(f"  Final conversion rate: {result.get('final_conversion_rate'):.1%}" if result.get('final_conversion_rate') else "  Final conversion rate: N/A")
        
        print(f"\n  Funnel steps:")
        for step in result.get('steps', []):
            conv_prev = f"({step['conversion_from_prev']:.1%} from prev)" if step['conversion_from_prev'] else ""
            conv_start = f"({step['conversion_from_start']:.1%} from start)" if step['conversion_from_start'] else ""
            device_filter = f"[device={step.get('device_type')}]" if step.get('device_type') else ""
            print(f"    [{step['step_index']}] {step['step_name']} {device_filter}: {step['count']} users {conv_prev} {conv_start}")
        
        cd_analysis = result.get('cross_device_analysis', {})
        if cd_analysis:
            print(f"\n  Cross-device analysis:")
            print(f"    Completed users: {cd_analysis.get('completed_users')}")
            for trans in cd_analysis.get('step_transitions', []):
                print(f"    {trans['from_step']} -> {trans['to_step']}:")
                same_rate = trans.get('same_device_rate')
                cross_rate = trans.get('cross_device_rate')
                print(f"      Same device: {trans['same_device_count']} ({same_rate:.1%})" if same_rate is not None else f"      Same device: {trans['same_device_count']} (N/A)")
                print(f"      Cross device: {trans['cross_device_count']} ({cross_rate:.1%})" if cross_rate is not None else f"      Cross device: {trans['cross_device_count']} (N/A)")
                for dt in trans.get('device_transitions', [])[:3]:
                    print(f"        {dt['from_device']} -> {dt['to_device']}: {dt['count']} ({dt['percentage']}%)")
    
    return result.get('success')

def test_segment_validation():
    print_separator("10. SEGMENT EXPRESSION VALIDATION")
    
    valid_expr = "past 30 days in 'ios' event_count 'page_view' >= 5 AND past 30 days in 'web' event_count 'order_completed' >= 1"
    invalid_expr = "past 30 days invalid_token 'page_view' >= 1"
    
    print("  Valid expression:")
    print(f"    {valid_expr}")
    result1 = api_post("/api/segments/validate", {"expression": valid_expr})
    print(f"    Result: valid={result1.get('valid')}, error={result1.get('error')}")
    
    print("\n  Invalid expression:")
    print(f"    {invalid_expr}")
    result2 = api_post("/api/segments/validate", {"expression": invalid_expr})
    print(f"    Result: valid={result2.get('valid')}, error={result2.get('error')}")
    if result2.get('suggestion'):
        print(f"    Suggestion: {result2.get('suggestion')}")
    
    return True

def test_segment_preview_and_create():
    print_separator("11. SEGMENT PREVIEW AND CREATE")
    
    expression = "past 30 days event_count 'page_view' >= 3"
    
    print("  Preview segment:")
    result = api_post("/api/segments/preview", {"expression": expression, "limit": 10})
    if result.get('success'):
        print(f"    Estimated members: {result.get('estimated_count')}")
        print(f"    Preview members: {result.get('preview_members')[:10]}")
    
    print("\n  Create segment:")
    result2 = api_post("/api/segments", {
        "name": "活跃用户群",
        "expression": expression,
        "description": "过去30天浏览过3次以上的用户",
        "subscribers": ["ops@example.com"]
    })
    if result2.get('success'):
        print(f"    Segment ID: {result2.get('segment_id')}")
        print(f"    Preview member count: {result2.get('preview_member_count')}")
    
    return result.get('success') and result2.get('success')

def test_segment_compare():
    print_separator("12. SEGMENT COMPARISON")
    
    segments = api_get("/api/segments")
    segment_ids = [s['segment_id'] for s in segments.get('segments', [])[:2]]
    
    if len(segment_ids) >= 2:
        result = api_post("/api/segments/compare", {
            "segment_ids": segment_ids,
            "metrics": ["retention", "active_frequency", "aov"]
        })
        
        if result.get('success'):
            print(f"  Comparing {len(segment_ids)} segments")
            print(f"  Metrics: {result.get('metrics')}")
            
            for seg_id, data in result.get('segment_data', {}).items():
                print(f"\n  {data.get('name')} ({seg_id}):")
                print(f"    Members: {data.get('member_count')}")
                freq = data.get('metrics', {}).get('active_frequency')
                if freq:
                    print(f"    Active frequency: avg={freq.get('avg')}, median={freq.get('median')}")
                aov = data.get('metrics', {}).get('aov')
                if aov:
                    print(f"    AOV: avg=¥{aov.get('avg')}, paying_users={aov.get('paying_users')}")
            
            if result.get('comparison'):
                print(f"\n  Comparison conclusions:")
                for conclusion in result.get('comparison', []):
                    print(f"    - {conclusion}")
    
    return True

def test_churn_rules():
    print_separator("13. CHURN RULES")
    
    print("  Create churn rule:")
    rule_data = {
        "name": "高风险流失用户",
        "conditions": [
            {"type": "no_activity", "days": 14},
            {"type": "no_purchase", "days": 30}
        ],
        "description": "过去14天无活跃且过去30天无消费的用户"
    }
    result = api_post("/api/churn/rules", rule_data)
    if result.get('success'):
        print(f"    Rule ID: {result.get('rule_id')}")
        rule_id = result.get('rule_id')
    
    print("\n  List all rules:")
    result2 = api_get("/api/churn/rules")
    if result2.get('success'):
        print(f"    Total rules: {len(result2.get('rules', []))}")
        for rule in result2.get('rules', []):
            print(f"      - {rule.get('name')}: {rule.get('description')}")
    
    return result.get('success') and result2.get('success')

def test_churn_run():
    print_separator("14. CHURN DETECTION RUN")
    
    rules = api_get("/api/churn/rules")
    rule_list = rules.get('rules', [])
    
    if rule_list:
        rule_id = rule_list[0]['rule_id']
        
        print(f"  Data integrity check:")
        integrity = api_get("/api/churn/data-integrity")
        print(f"    Data lag: {integrity.get('data_lag_hours')}h")
        print(f"    Is complete: {integrity.get('is_data_complete_for_churn')}")
        print(f"    Threshold: {integrity.get('threshold_hours')}h")
        
        print(f"\n  Running churn detection (rule_id={rule_id}):")
        print(f"  Note: Skipping data integrity check for testing...")
        result = api_post(f"/api/churn/run/{rule_id}", {
            "check_data_integrity": False
        })
        
        if result.get('success'):
            print(f"    Run time: {datetime.fromtimestamp(result.get('run_time')).isoformat() if result.get('run_time') else 'N/A'}")
            print(f"    Total users checked: {result.get('total_users_checked')}")
            print(f"    Churn users found: {result.get('churn_users_found')}")
            print(f"    Already reached: {result.get('already_reached')}")
            print(f"    Recall success: {result.get('recall_success_count')}")
            print(f"    Severity distribution: {result.get('severity_distribution')}")
            
            if result.get('results'):
                print(f"\n    Top 5 churn users:")
                for churn in result.get('results', [])[:5]:
                    reason_desc = churn['reasons'][0]['description'] if churn.get('reasons') else "N/A"
                    print(f"      {churn['user_id']}: {churn['last_active_days']} days inactive, severity={churn['top_severity']}")
                    print(f"        Reason: {reason_desc[:80]}...")
    
    return result.get('success', False) if 'result' in locals() else True

def test_churn_reach():
    print_separator("15. CHURN REACH AND RECALL EVALUATION")
    
    rules = api_get("/api/churn/rules")
    rule_list = rules.get('rules', [])
    
    if rule_list:
        rule_id = rule_list[0]['rule_id']
        
        churn_results = api_get("/api/churn/results", {"rule_id": rule_id, "limit": 5})
        churn_users = [r['user_id'] for r in churn_results.get('results', [])[:3]]
        
        if churn_users:
            print(f"  Recording reach for users: {churn_users}")
            result = api_post("/api/churn/reach", {
                "rule_id": rule_id,
                "user_ids": churn_users,
                "channel": "sms",
                "content": "【活动邀请】亲爱的用户，我们想念您！回来看看吧~"
            })
            if result.get('success'):
                print(f"    Attempted: {result.get('attempted')}")
                print(f"    Recorded: {result.get('recorded')}")
                print(f"    Skipped: {result.get('skipped_due_to_frequency')}")
        
        print(f"\n  Reach history:")
        history = api_get("/api/churn/reach-history", {"rule_id": rule_id})
        if history.get('success'):
            print(f"    Total records: {history.get('total')}")
        
        print(f"\n  Evaluate recall:")
        recall_result = api_post("/api/churn/evaluate-recall", {"rule_id": rule_id})
        if recall_result.get('success'):
            print(f"    Evaluated: {recall_result.get('evaluated')}")
            print(f"    Recalled: {recall_result.get('recalled')}")
            print(f"    Recall rate: {recall_result.get('recall_rate')}")
    
    return True

def main():
    tests = [
        ("Health Check", test_health),
        ("Event Statistics", test_event_stats),
        ("Device Overlap", test_device_overlap),
        ("Cohort Analysis", test_cohort_analyze),
        ("Cross-Device Timeline", test_crossdevice_timeline),
        ("Cross-Device Switch Frequency", test_crossdevice_switch_frequency),
        ("Cross-Device Duration", test_crossdevice_duration),
        ("Cross-Device Conversion Paths", test_crossdevice_conversion_paths),
        ("Cross-Device Funnel", test_crossdevice_funnel),
        ("Segment Validation", test_segment_validation),
        ("Segment Preview & Create", test_segment_preview_and_create),
        ("Segment Compare", test_segment_compare),
        ("Churn Rules", test_churn_rules),
        ("Churn Detection", test_churn_run),
        ("Churn Reach & Recall", test_churn_reach),
    ]
    
    print(f"\n{'#'*80}")
    print(f"  Cross-Device Retention Analysis - API Test Suite")
    print(f"  Started at: {datetime.now().isoformat()}")
    print(f"  Target: {BASE_URL}")
    print(f"{'#'*80}")
    
    passed = 0
    failed = 0
    errors = []
    
    for name, test_func in tests:
        try:
            result = test_func()
            if result:
                passed += 1
            else:
                failed += 1
                errors.append(name)
        except Exception as e:
            failed += 1
            errors.append(f"{name} (exception: {e})")
    
    print(f"\n{'#'*80}")
    print(f"  Test Results: {passed} passed, {failed} failed, {passed + failed} total")
    if errors:
        print(f"  Failed tests:")
        for err in errors:
            print(f"    - {err}")
    print(f"{'#'*80}")
    
    return failed == 0

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)