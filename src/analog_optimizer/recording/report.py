"""Human-readable view of the same versioned overview used by control scripts."""
import json


def format_overview(data):
    summary = data['summary']
    states = {'open': '未登记结束（不代表进程仍存活）', 'ended': '已登记结束',
              'ended_with_pending': '已登记结束，但仍有未完成评价'}
    outcomes = summary['outcome_counts']
    pending = sum(data['pending_by_state'].values())
    lines = [f"Run: {data['run_id']}", f"状态: {states[data['lifecycle']]}",
             f"进度: {summary['evaluations']} 次已提交评价；{pending} 次未完成；累计 {summary['wall_seconds']:.2f} s",
             f"评价结果（含验证）: 达标 {outcomes.get('feasible', 0)} / 未达标 {outcomes.get('infeasible', 0)} / 失败 {outcomes.get('failed', 0)}",
             f"真实仿真: 已确认 {summary['real_simulations']}；调用不确定 {summary.get('unconfirmed_invocations', 0)}；缓存 {summary['cache_hits']}",
             f"来源: {json.dumps(summary['source_counts'], ensure_ascii=False)}",
             f"错误分类: {json.dumps(summary['error_counts'], ensure_ascii=False)}",
             f"未完成登记: {json.dumps(data['pending_by_state'], ensure_ascii=False)}",
             f"可行设计: {'已找到' if summary['has_feasible'] else '尚未找到'}；仅表示已观察到的结果",
             f"选择规则: {json.dumps(summary['selection'], ensure_ascii=False)}"]
    first = summary['first_feasible']
    if first:
        lines.append(f"首次达标: {first['seconds']:.2f} s / 已确认真实调用 {first['real_simulations']}；eval {first['eval_id']}")
    for key, label in [('initial', '初始设计'), ('best_feasible', '最佳可行设计'), ('best_infeasible', '最小约束违反设计')]:
        candidate = summary[key]
        lines.append(f"{label}: {'无' if candidate is None else candidate['eval_id']}")
        if candidate is None:
            continue
        parameters = candidate['parameters'] or {}
        if isinstance(parameters, dict):
            parameters = {('/'.join(k) if isinstance(k, tuple) else str(k)): v for k, v in parameters.items()}
        lines.append('  实际参数: ' + json.dumps(parameters, ensure_ascii=False))
        for constraint in candidate['constraints']:
            c = constraint
            status = '无效/缺失' if not c['valid'] else '满足' if c['met'] else '未满足'
            bounds = f"[{c['lower']}, {c['upper']}]"
            role = '停用' if not c['active'] else '必需' if c['required'] else '可选'
            lines.append(f"  {c['metric']}: {c['value']} {c['unit']}；范围 {bounds}；{role}，{status}")
    checkpoint = data['latest_checkpoint']
    lines.append('最新完整 checkpoint: ' + ('无' if checkpoint is None else f"step {checkpoint['step']} / {checkpoint['path']}"))
    lines.append('最近评价（新到旧）:')
    for row in data['recent_evaluations']:
        lines.append(f"  {row['eval_id']}  {row['phase']}  worker={row['worker_id']} episode={row['episode_id']} step={row['step']}  {row['status'] or row['state']}")
        if row['error_summary']:
            # The database retains the full bounded error; keep terminal output short.
            lines.append('    ' + row['error_summary'][:240].replace('\n', ' '))
    sizes = data['storage']['bytes']
    lines.append('本地记录目录占用（不含远端/其他目录）:')
    for key in ('database', 'journal', 'attachments', 'checkpoints', 'temporary', 'other', 'total', 'filesystem_free'):
        lines.append(f"  {key}: {sizes[key]} B ({sizes[key] / 1024**2:.2f} MiB)")
    return '\n'.join(lines)
