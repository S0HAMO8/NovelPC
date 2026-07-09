"""
Rule-based "Build Advisor" — NOT a real AI model, just clear Python logic.
Given a use-case (gaming / editing / streaming / office) and a budget (INR),
picks one component per category that fits, then tries to upgrade components
within the same total budget by swapping in higher performance_score items.

Rules encoded here (per reviewer feedback):
  - Item 4:  if the budget can't cover a valid build, return an explicit
             "can't build in this budget" response instead of a partial/broken build.
  - Item 9:  'office' and 'editing' use-cases never get a GPU or any cooling
             upgrade (air/liquid) — they rely on integrated graphics & stock cooling.
  - Item 10: 'gaming' use-case adds extra case fans when the budget allows.
  - Item 13: every recommended build is run back through the real compatibility
             checks (form factor, RAM type, GPU fit, PSU wattage) before being
             returned, and the picker actively avoids combinations that would fail.
"""

from compatibility import run_all_checks, check_form_factor, check_cpu_socket

# Category budget allocation per use-case. Categories not relevant to a use-case
# (e.g. gpu/cooling for office) are simply absent or zeroed and skipped entirely.
BUDGET_SPLIT = {
    'gaming':    {'gpu': 0.35, 'cpu': 0.18, 'motherboard': 0.10, 'ram': 0.08,
                  'ssd': 0.08, 'psu': 0.08, 'cabinet': 0.06, 'cooling': 0.05, 'fan': 0.02},
    'editing':   {'cpu': 0.32, 'motherboard': 0.13, 'ram': 0.18,
                  'ssd': 0.18, 'psu': 0.11, 'cabinet': 0.08},
    'streaming': {'gpu': 0.28, 'cpu': 0.22, 'motherboard': 0.10, 'ram': 0.10,
                  'ssd': 0.10, 'psu': 0.08, 'cabinet': 0.05, 'cooling': 0.07},
    'office':    {'cpu': 0.34, 'motherboard': 0.16, 'ram': 0.16,
                  'ssd': 0.16, 'psu': 0.10, 'cabinet': 0.08},
}

# Which component categories are mandatory for a complete, working PC per use-case.
# 'office' and 'editing' (item 9) deliberately exclude gpu/air_cooler/liquid_cooler.
REQUIRED_BY_USECASE = {
    'gaming':    ['cpu', 'gpu', 'motherboard', 'ram', 'ssd', 'psu', 'cabinet'],
    'streaming': ['cpu', 'gpu', 'motherboard', 'ram', 'ssd', 'psu', 'cabinet'],
    'editing':   ['cpu', 'motherboard', 'ram', 'ssd', 'psu', 'cabinet'],
    'office':    ['cpu', 'motherboard', 'ram', 'ssd', 'psu', 'cabinet'],
}

# Whether a use-case includes a dedicated cooling solution (air or liquid) at all.
USES_DEDICATED_COOLING = {
    'gaming': True,
    'streaming': True,
    'editing': False,   # item 9: no air/liquid cooler for editing
    'office': False,    # item 9: no air/liquid cooler for office
}

# Whether a use-case can include extra case fans if budget allows (item 10: gaming only).
USES_EXTRA_FANS = {
    'gaming': True,
    'streaming': False,
    'editing': False,
    'office': False,
}


def _cheapest_in_stock(components):
    in_stock = [c for c in components if c.get('stock')]
    if not in_stock:
        return None
    return min(in_stock, key=lambda c: c['price'])


def _best_within_budget(components, category_budget):
    """From a list of in-stock component dicts, pick the highest performance_score
    item whose price is <= category_budget. Falls back to the cheapest in-stock item
    if nothing fits the budget (caller decides whether that's acceptable)."""
    in_stock = [c for c in components if c.get('stock')]
    if not in_stock:
        return None
    affordable = [c for c in in_stock if c['price'] <= category_budget]
    if affordable:
        return max(affordable, key=lambda c: c['performance_score'])
    return min(in_stock, key=lambda c: c['price'])


def _cheapest_compatible_core_combo(all_components):
    """Finds the cheapest mutually-compatible (motherboard, cpu, ram, cabinet) combo —
    CPU socket matches motherboard socket, RAM type matches motherboard, and
    motherboard form factor fits the cabinet. This reflects the real constraints
    the allocator has to satisfy, so the 'minimum possible cost' estimate doesn't
    undercount by assuming independently-cheapest parts can always be combined
    (item 4 fix, plus the newly-added CPU<->motherboard socket check)."""
    mobos = [m for m in all_components.get('motherboard', []) if m.get('stock')]
    cabinets = [c for c in all_components.get('cabinet', []) if c.get('stock')]
    rams = [r for r in all_components.get('ram', []) if r.get('stock')]
    cpus = [c for c in all_components.get('cpu', []) if c.get('stock')]
    if not mobos or not cabinets or not rams or not cpus:
        return None

    best_total = None
    # Small catalogs make this cheap enough; correctness matters more than micro-optimizing.
    for mb in sorted(mobos, key=lambda m: m['price'])[:10]:
        mb_socket = mb.get('specs', {}).get('socket', '').upper()
        mb_ram_type = mb.get('specs', {}).get('ram_type', '').upper()

        matching_cpus = [c for c in cpus if c.get('specs', {}).get('socket', '').upper() == mb_socket]
        if not matching_cpus:
            continue
        cheapest_cpu = min(matching_cpus, key=lambda c: c['price'])

        matching_rams = [r for r in rams if r.get('specs', {}).get('type', '').upper() == mb_ram_type]
        if not matching_rams:
            continue
        cheapest_ram = min(matching_rams, key=lambda r: r['price'])

        for cab in sorted(cabinets, key=lambda c: c['price']):
            ok, _ = check_form_factor(mb, cab)
            if not ok:
                continue
            combo_total = mb['price'] + cheapest_cpu['price'] + cheapest_ram['price'] + cab['price']
            if best_total is None or combo_total < best_total:
                best_total = combo_total
            break  # cabinets sorted by price; first compatible one is cheapest for this mb

    return best_total


def _minimum_possible_cost(all_components, use_case):
    """The cheapest possible total for a valid build of this use-case, used to
    detect a too-small budget (item 4) before we even try to allocate by category.

    Accounts for the CPU<->motherboard socket and motherboard<->RAM<->cabinet
    compatibility constraints (item 13) instead of naively summing
    independently-cheapest parts, which previously underestimated the true
    minimum and let through budgets that were actually too small once
    compatibility was enforced.
    """
    required = REQUIRED_BY_USECASE.get(use_case, REQUIRED_BY_USECASE['gaming'])
    total = 0
    missing = []

    needs_core_combo = all(t in required for t in ('cpu', 'motherboard', 'ram', 'cabinet'))
    if needs_core_combo:
        combo_total = _cheapest_compatible_core_combo(all_components)
        if combo_total is None:
            missing.append('cpu/motherboard/ram/cabinet')
        else:
            total += combo_total
        remaining_types = [t for t in required if t not in ('cpu', 'motherboard', 'ram', 'cabinet')]
    else:
        remaining_types = required

    for ctype in remaining_types:
        cheapest = _cheapest_in_stock(all_components.get(ctype, []))
        if cheapest is None:
            missing.append(ctype)
            continue
        total += cheapest['price']

    if USES_DEDICATED_COOLING.get(use_case):
        air = _cheapest_in_stock(all_components.get('air_cooler', []))
        liquid = _cheapest_in_stock(all_components.get('liquid_cooler', []))
        options = [c for c in [air, liquid] if c]
        if options:
            total += min(options, key=lambda c: c['price'])['price']
        else:
            missing.append('cooling')

    return total, missing


def _pick_compatible_motherboard_cabinet(mobos, cabinets, mb_budget, cab_budget):
    """Item 13: choose a motherboard+cabinet pair that actually passes the
    form-factor compatibility check, not just whatever is cheapest/best individually.

    Budget fit is treated as a HARD preference: we first search only among pairs
    that together fit within (mb_budget + cab_budget). Only if no compatible pair
    exists at all within that combined budget do we fall back to the cheapest
    compatible pair regardless of price — this avoids silently recommending a
    motherboard+cabinet combo that blows through the budget just because it was
    the first compatible pair found.
    """
    mobos_stock = [m for m in mobos if m.get('stock')]
    cabinets_stock = [c for c in cabinets if c.get('stock')]
    if not mobos_stock or not cabinets_stock:
        return None, None

    combined_budget = mb_budget + cab_budget

    # Pass 1: only consider compatible pairs whose combined price fits the budget;
    # among those, pick the one with the best combined performance.
    in_budget_pairs = []
    for mb in mobos_stock:
        for cab in cabinets_stock:
            if mb['price'] + cab['price'] <= combined_budget:
                ok, _ = check_form_factor(mb, cab)
                if ok:
                    in_budget_pairs.append((mb, cab))
    if in_budget_pairs:
        best = max(in_budget_pairs, key=lambda pair: pair[0]['performance_score'] + pair[1]['performance_score'])
        return best

    # Pass 2: no compatible pair fits the budget — fall back to the CHEAPEST
    # compatible pair available (not the highest-performance one), so we stay
    # as close to budget as possible rather than overshooting it dramatically.
    cheapest_pair = None
    cheapest_price = None
    for mb in sorted(mobos_stock, key=lambda m: m['price']):
        for cab in sorted(cabinets_stock, key=lambda c: c['price']):
            ok, _ = check_form_factor(mb, cab)
            if ok:
                combo_price = mb['price'] + cab['price']
                if cheapest_price is None or combo_price < cheapest_price:
                    cheapest_price = combo_price
                    cheapest_pair = (mb, cab)
        # Small optimization: once we've found any compatible pair with this (cheapest) mb,
        # later more expensive motherboards can't beat it paired with the cheapest cabinet,
        # but we keep the loop simple/correct rather than over-optimizing.

    if cheapest_pair:
        return cheapest_pair
    return min(mobos_stock, key=lambda m: m['price']), min(cabinets_stock, key=lambda c: c['price'])


def _pick_compatible_cpu(cpus, motherboard, cpu_budget):
    """Item 13 (socket check): only consider CPUs whose socket matches the chosen motherboard."""
    if not motherboard:
        return _best_within_budget(cpus, cpu_budget)
    mb_socket = motherboard.get('specs', {}).get('socket', '').upper()
    matching = [c for c in cpus if c.get('stock') and c.get('specs', {}).get('socket', '').upper() == mb_socket]
    if matching:
        affordable = [c for c in matching if c['price'] <= cpu_budget]
        if affordable:
            return max(affordable, key=lambda c: c['performance_score'])
        return min(matching, key=lambda c: c['price'])
    return _best_within_budget(cpus, cpu_budget)


def _pick_compatible_ram(rams, motherboard, ram_budget):
    """Item 13: only consider RAM whose type matches the chosen motherboard."""
    if not motherboard:
        return _best_within_budget(rams, ram_budget)
    mb_ram_type = motherboard.get('specs', {}).get('ram_type', '').upper()
    matching = [r for r in rams if r.get('stock') and r.get('specs', {}).get('type', '').upper() == mb_ram_type]
    if matching:
        affordable = [r for r in matching if r['price'] <= ram_budget]
        if affordable:
            return max(affordable, key=lambda c: c['performance_score'])
        return min(matching, key=lambda c: c['price'])
    return _best_within_budget(rams, ram_budget)


def _pick_compatible_gpu(gpus, cabinet, gpu_budget):
    """Item 13: only consider GPUs that physically fit the chosen cabinet."""
    if not cabinet:
        return _best_within_budget(gpus, gpu_budget)
    cab_max_len = cabinet.get('specs', {}).get('max_gpu_length_mm', 9999)
    fitting = [g for g in gpus if g.get('stock') and g.get('specs', {}).get('length_mm', 0) <= cab_max_len]
    if fitting:
        affordable = [g for g in fitting if g['price'] <= gpu_budget]
        if affordable:
            return max(affordable, key=lambda c: c['performance_score'])
        return min(fitting, key=lambda c: c['price'])
    return _best_within_budget(gpus, gpu_budget)


def _effective_total(picks, ram_quantity, fan_quantity):
    """Sum of pick prices, correctly multiplying RAM and fan by their quantities
    instead of treating them as single units (bug fix: RAM x2/x4 and fan xN must
    actually cost N times the unit price, not just the price of one stick/fan)."""
    total = 0
    for ctype, comp in picks.items():
        if ctype == 'ram':
            total += comp['price'] * ram_quantity
        elif ctype == 'fan':
            total += comp['price'] * fan_quantity
        else:
            total += comp['price']
    return total


def _effective_wattage(picks, ram_quantity, fan_quantity):
    """Sum of pick wattages, correctly multiplying RAM and fan by their quantities."""
    total = 0
    for ctype, comp in picks.items():
        if ctype == 'ram':
            total += comp.get('wattage', 0) * ram_quantity
        elif ctype == 'fan':
            total += comp.get('wattage', 0) * fan_quantity
        else:
            total += comp.get('wattage', 0)
    return total


def recommend_build(all_components, use_case, budget):
    """
    all_components: dict {type: [component_dict, ...]}
    use_case: 'gaming' | 'editing' | 'streaming' | 'office'
    budget: float (INR)

    Returns either:
      { 'error': 'cant_build', 'message': str, 'minimum_required': float (optional) }
      or
      { 'picks': {type: component_dict}, 'total': float, 'notes': [str, ...],
        'remaining': float, 'ram_quantity': int, 'fan_quantity': int, 'cooling_type': str|None }
    """
    use_case = use_case if use_case in BUDGET_SPLIT else 'gaming'
    split = BUDGET_SPLIT[use_case]
    required = REQUIRED_BY_USECASE[use_case]

    # ── Item 4: budget-too-low guard, checked BEFORE attempting allocation ──
    min_cost, missing_categories = _minimum_possible_cost(all_components, use_case)
    if missing_categories:
        return {
            'error': 'cant_build',
            'message': f"We don't currently have in-stock options for: {', '.join(missing_categories)}. "
                       f"A complete build can't be assembled right now."
        }
    if budget < min_cost:
        return {
            'error': 'cant_build',
            'message': f"Sorry, ₹{budget:,.0f} isn't enough to build a complete {use_case} PC. "
                       f"The cheapest possible complete build for this use-case costs around ₹{min_cost:,.0f}. "
                       f"Please increase your budget or choose a different use-case.",
            'minimum_required': min_cost,
        }

    picks = {}
    notes = []

    # ── Step 1: Motherboard + Cabinet chosen together for compatibility (item 13) ──
    mb_budget = budget * split.get('motherboard', 0.10)
    cab_budget = budget * split.get('cabinet', 0.06)
    mb, cab = _pick_compatible_motherboard_cabinet(
        all_components.get('motherboard', []), all_components.get('cabinet', []),
        mb_budget, cab_budget
    )
    if mb:
        picks['motherboard'] = mb
    if cab:
        picks['cabinet'] = cab

    # ── Step 2: CPU — must match motherboard socket (item 13) ──
    if 'cpu' in required:
        cpu_budget = budget * split.get('cpu', 0.20)
        cpu = _pick_compatible_cpu(all_components.get('cpu', []), picks.get('motherboard'), cpu_budget)
        if cpu:
            picks['cpu'] = cpu

    # ── Step 3: RAM — must match motherboard DDR type (item 13) ──
    ram_quantity = 2
    if 'ram' in required:
        ram_budget = budget * split.get('ram', 0.10)
        ram = _pick_compatible_ram(all_components.get('ram', []), picks.get('motherboard'), ram_budget)
        if ram:
            picks['ram'] = ram

    # ── Step 4: GPU — only for gaming/streaming (item 9), must fit cabinet (item 13) ──
    if 'gpu' in required:
        gpu_budget = budget * split.get('gpu', 0.30)
        gpu = _pick_compatible_gpu(all_components.get('gpu', []), picks.get('cabinet'), gpu_budget)
        if gpu:
            picks['gpu'] = gpu

    # ── Step 5: Storage (SSD always; HDD optional, not required) ──
    if 'ssd' in required:
        ssd_budget = budget * split.get('ssd', 0.10)
        ssd = _best_within_budget(all_components.get('ssd', []), ssd_budget)
        if ssd:
            picks['ssd'] = ssd

    # ── Step 6: Cooling — only for gaming/streaming (item 9) ──
    # Gaming rules:
    #   budget < 50000  → air cooler only
    #   50000–100000    → liquid cooler only
    #   > 100000        → both liquid cooler AND air cooler
    cooling_type_used = None
    if USES_DEDICATED_COOLING.get(use_case):
        # Use a generous fixed cooling budget so liquid coolers are actually reachable.
        # Percentage-based budgets (5% of 100000 = 5000) are too small for liquid coolers.
        if budget >= 100000:
            cooling_budget = budget * 0.08
        elif budget >= 50000:
            cooling_budget = budget * 0.07
        else:
            cooling_budget = budget * 0.06

        in_stock_liquid = [c for c in all_components.get('liquid_cooler', []) if c.get('stock')]
        in_stock_air    = [c for c in all_components.get('air_cooler', [])    if c.get('stock')]

        if use_case == 'gaming' and budget > 100000:
            # Both coolers
            liquid = (max([c for c in in_stock_liquid if c['price'] <= cooling_budget],
                          key=lambda c: c['performance_score'], default=None)
                      or (min(in_stock_liquid, key=lambda c: c['price']) if in_stock_liquid else None))
            if liquid:
                picks['liquid_cooler'] = liquid
                cooling_type_used = 'liquid_cooler'

            air = (max([c for c in in_stock_air if c['price'] <= cooling_budget],
                       key=lambda c: c['performance_score'], default=None)
                   or (min(in_stock_air, key=lambda c: c['price']) if in_stock_air else None))
            if air:
                picks['air_cooler'] = air
                cooling_type_used = 'both'

        elif use_case == 'gaming' and budget < 50000:
            # Air cooler only
            air = (max([c for c in in_stock_air if c['price'] <= cooling_budget],
                       key=lambda c: c['performance_score'], default=None)
                   or (min(in_stock_air, key=lambda c: c['price']) if in_stock_air else None))
            if air:
                picks['air_cooler'] = air
                cooling_type_used = 'air_cooler'

        else:
            # 50000–100000 gaming, or streaming — liquid cooler preferred
            liquid = (max([c for c in in_stock_liquid if c['price'] <= cooling_budget],
                          key=lambda c: c['performance_score'], default=None)
                      or (min(in_stock_liquid, key=lambda c: c['price']) if in_stock_liquid else None))
            if liquid:
                picks['liquid_cooler'] = liquid
                cooling_type_used = 'liquid_cooler'
            else:
                # No liquid in stock at all — fallback to air
                air = (max([c for c in in_stock_air if c['price'] <= cooling_budget],
                           key=lambda c: c['performance_score'], default=None)
                       or (min(in_stock_air, key=lambda c: c['price']) if in_stock_air else None))
                if air:
                    picks['air_cooler'] = air
                    cooling_type_used = 'air_cooler'

    # ── Step 7: PSU — sized using an estimated system wattage ──
    if 'psu' in required:
        est_wattage = _effective_wattage(picks, ram_quantity, 0)  # fans not chosen yet at this step
        required_watts = int(est_wattage * 1.2)
        psu_budget = budget * split.get('psu', 0.08)
        candidates = [p for p in all_components.get('psu', []) if p.get('stock')]
        sufficient = [p for p in candidates if p.get('specs', {}).get('wattage', p.get('wattage', 0)) >= required_watts]
        if sufficient:
            affordable = [p for p in sufficient if p['price'] <= psu_budget]
            psu = max(affordable, key=lambda c: c['performance_score']) if affordable else min(sufficient, key=lambda c: c['price'])
        else:
            psu = max(candidates, key=lambda c: c.get('specs', {}).get('wattage', 0)) if candidates else None
        if psu:
            picks['psu'] = psu

    total = _effective_total(picks, ram_quantity, 0)
    remaining = budget - total

    # ── Step 8: Extra fans — gaming only, only if budget allows (item 10) ──
    fan_quantity = 0
    if USES_EXTRA_FANS.get(use_case) and remaining > 0:
        fan_budget = budget * split.get('fan', 0.02)
        fan_options = [f for f in all_components.get('fan', []) if f.get('stock')]
        affordable_fans = [f for f in fan_options if f['price'] <= max(fan_budget, remaining)]
        if affordable_fans:
            best_fan = max(affordable_fans, key=lambda c: c['performance_score'])
            qty = 1
            if remaining - best_fan['price'] >= best_fan['price']:
                qty = 2
            fan_cost = best_fan['price'] * qty
            if fan_cost <= remaining:
                picks['fan'] = best_fan
                fan_quantity = qty
                total += fan_cost
                remaining -= fan_cost
                notes.append(f"Added {qty}x {best_fan['name']} (+₹{fan_cost:,.0f}) for better airflow within your budget.")

    # ── Step 9: Spend any leftover budget on performance upgrades ──
    if remaining > 0:
        for ctype in list(picks.keys()):
            if ctype == 'fan':
                continue  # fan quantity already optimized above
            real_type = ctype   # key is already the real type (air_cooler / liquid_cooler)
            candidates = [c for c in all_components.get(real_type, []) if c.get('stock')]
            current = picks[ctype]
            qty_multiplier = ram_quantity if ctype == 'ram' else 1
            better_options = [
                c for c in candidates
                if c['performance_score'] > current['performance_score']
                and (c['price'] - current['price']) * qty_multiplier <= remaining
            ]
            if ctype == 'ram' and picks.get('motherboard'):
                mb_type = picks['motherboard'].get('specs', {}).get('ram_type', '').upper()
                better_options = [c for c in better_options if c.get('specs', {}).get('type', '').upper() == mb_type]
            if ctype == 'cpu' and picks.get('motherboard'):
                mb_socket = picks['motherboard'].get('specs', {}).get('socket', '').upper()
                better_options = [c for c in better_options if c.get('specs', {}).get('socket', '').upper() == mb_socket]
            if ctype == 'gpu' and picks.get('cabinet'):
                cab_max = picks['cabinet'].get('specs', {}).get('max_gpu_length_mm', 9999)
                better_options = [c for c in better_options if c.get('specs', {}).get('length_mm', 0) <= cab_max]
            if ctype == 'motherboard' and picks.get('cabinet'):
                better_options = [c for c in better_options if check_form_factor(c, picks['cabinet'])[0]]
            if ctype == 'motherboard' and picks.get('cpu'):
                cpu_socket = picks['cpu'].get('specs', {}).get('socket', '').upper()
                better_options = [c for c in better_options if c.get('specs', {}).get('socket', '').upper() == cpu_socket]
            if ctype == 'cabinet' and picks.get('motherboard'):
                better_options = [c for c in better_options if check_form_factor(picks['motherboard'], c)[0]]

            if better_options:
                upgrade = max(better_options, key=lambda c: c['performance_score'])
                diff = (upgrade['price'] - current['price']) * qty_multiplier
                remaining -= diff
                notes.append(
                    f"Upgraded {real_type.upper().replace('_',' ')} from {current['name']} to {upgrade['name']} "
                    f"(+₹{diff:,.0f}) — better performance, same overall budget."
                )
                picks[ctype] = upgrade

    total = _effective_total(picks, ram_quantity, fan_quantity)
    remaining = budget - total

    # ── Item 13: final safety net — run the real compatibility engine ──
    build_dict_for_check = {
        'motherboard': picks.get('motherboard'),
        'cabinet': picks.get('cabinet'),
        'ram': picks.get('ram'),
        'gpu': picks.get('gpu'),
        'psu': picks.get('psu'),
        'cpu': picks.get('cpu'),
    }
    check_results = run_all_checks(build_dict_for_check, ram_quantity)
    failed_checks = [c for c in check_results if c['status'] == 'fail']
    if failed_checks:
        for fc in failed_checks:
            notes.append(f"⚠️ Compatibility note — {fc['component']}: {fc['message']}")

    missing = [t for t in required if t not in picks]
    if missing:
        notes.append(f"Could not find suitable in-stock options for: {', '.join(missing)}.")
    if remaining < 0:
        overrun_pct = (abs(remaining) / budget) * 100 if budget > 0 else 0
        if overrun_pct > 15:
            notes.append(
                f"⚠️ This build exceeds your budget by ₹{abs(remaining):,.0f} ({overrun_pct:.0f}% over). "
                f"The cheapest available compatible components for this use-case still cost more than your budget allows — "
                f"consider increasing your budget or removing optional categories."
            )
        else:
            notes.append(f"This build slightly exceeds your budget by ₹{abs(remaining):,.0f} due to limited stock options.")
    elif remaining > 0:
        notes.append(f"₹{remaining:,.0f} left unspent — all picks already maximize performance within budget.")

    return {
        'picks': picks,
        'total': total,
        'notes': notes,
        'remaining': remaining,
        'ram_quantity': ram_quantity,
        'fan_quantity': fan_quantity,
        'cooling_type': cooling_type_used,
    }
