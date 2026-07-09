"""
Compatibility logic for the PC Builder.
All functions take component dicts (from Component.to_dict()) and return (bool, message).
"""

FORM_FACTOR_COMPAT = {
    'Full Tower': ['ATX', 'Micro-ATX', 'Mini-ITX'],
    'Mid Tower':  ['ATX', 'Micro-ATX', 'Mini-ITX'],
    'Mini Tower': ['Micro-ATX', 'Mini-ITX'],
    'Mini-ITX Case': ['Mini-ITX'],
}

def check_cpu_socket(cpu, motherboard):
    """Checks that the CPU's socket matches the motherboard's socket
    (e.g. AM4 CPU cannot physically go into an AM5 motherboard)."""
    if not cpu or not motherboard:
        return True, "Awaiting selection"
    cpu_socket = cpu.get('specs', {}).get('socket', '').upper()
    mb_socket = motherboard.get('specs', {}).get('socket', '').upper()
    if not cpu_socket or not mb_socket:
        return True, "Socket info not available."
    if cpu_socket == mb_socket:
        return True, f"CPU socket {cpu_socket} matches motherboard socket {mb_socket}."
    return False, f"CPU socket {cpu_socket} does NOT match motherboard socket {mb_socket}. These are physically incompatible!"


def check_form_factor(motherboard, cabinet):
    if not motherboard or not cabinet:
        return True, "Awaiting selection"
    mb_ff = motherboard.get('form_factor', '').strip()
    cab_ff = cabinet.get('form_factor', '').strip()
    supported = FORM_FACTOR_COMPAT.get(cab_ff, [])
    if mb_ff in supported:
        return True, f"{mb_ff} motherboard fits in {cab_ff} cabinet."
    return False, f"{mb_ff} motherboard does NOT fit in a {cab_ff} cabinet. Supported: {', '.join(supported)}."


def check_ram_compatibility(ram, motherboard, ram_quantity=1):
    """Checks RAM type match AND that the requested quantity doesn't exceed motherboard slots."""
    if not ram or not motherboard:
        return True, "Awaiting selection"
    ram_specs = ram.get('specs', {})
    mb_specs = motherboard.get('specs', {})
    ram_type = ram_specs.get('type', '').upper()
    mb_ram = mb_specs.get('ram_type', '').upper()
    mb_slots = motherboard.get('ram_slots', 4) or 4

    if ram_type and mb_ram and ram_type != mb_ram:
        return False, f"RAM is {ram_type} but motherboard supports {mb_ram}. Incompatible!"

    if ram_quantity > mb_slots:
        return False, f"You selected {ram_quantity} RAM stick(s) but this motherboard only has {mb_slots} slots."

    return True, f"{ram_type} RAM ({ram_quantity}x) is compatible — using {ram_quantity}/{mb_slots} slots."


def check_gpu_fit(gpu, cabinet):
    if not gpu or not cabinet:
        return True, "Awaiting selection"
    gpu_specs = gpu.get('specs', {})
    cab_specs = cabinet.get('specs', {})
    gpu_len = gpu_specs.get('length_mm', 0)
    cab_max = cab_specs.get('max_gpu_length_mm', 9999)
    if gpu_len == 0 or cab_max == 9999:
        return True, "GPU length info not available."
    if gpu_len <= cab_max:
        return True, f"GPU ({gpu_len}mm) fits in cabinet (max {cab_max}mm)."
    return False, f"GPU is {gpu_len}mm long but cabinet only supports up to {cab_max}mm!"


def check_psu_wattage(components_list, ram_quantity=1):
    psu = None
    total_tdp = 0
    for comp in components_list:
        if not comp:
            continue
        if comp.get('type') == 'psu':
            psu = comp
        elif comp.get('type') == 'ram':
            total_tdp += comp.get('wattage', 0) * ram_quantity
        else:
            total_tdp += comp.get('wattage', 0)
    if not psu:
        return True, "Awaiting PSU selection"
    psu_specs = psu.get('specs', {})
    psu_watts = psu_specs.get('wattage', psu.get('wattage', 0))
    required = int(total_tdp * 1.2)
    if psu_watts >= required:
        return True, f"PSU ({psu_watts}W) covers system TDP {total_tdp}W + 20% headroom ({required}W required)."
    return False, f"PSU ({psu_watts}W) is underpowered! System needs ~{required}W (TDP {total_tdp}W + 20% headroom)."


def run_all_checks(build_dict, ram_quantity=1):
    """
    build_dict keys: cpu, gpu, motherboard, ram, ssd, hdd, psu, cabinet,
                      air_cooler OR liquid_cooler, fan (optional)
    """
    results = []
    mb  = build_dict.get('motherboard')
    cab = build_dict.get('cabinet')
    ram = build_dict.get('ram')
    gpu = build_dict.get('gpu')
    cpu = build_dict.get('cpu')

    ok, msg = check_cpu_socket(cpu, mb)
    results.append({'component': 'CPU ↔ Motherboard', 'status': 'ok' if ok else 'fail', 'message': msg})

    ok, msg = check_form_factor(mb, cab)
    results.append({'component': 'Motherboard ↔ Cabinet', 'status': 'ok' if ok else 'fail', 'message': msg})

    ok, msg = check_ram_compatibility(ram, mb, ram_quantity)
    results.append({'component': 'RAM ↔ Motherboard', 'status': 'ok' if ok else 'fail', 'message': msg})

    ok, msg = check_gpu_fit(gpu, cab)
    results.append({'component': 'GPU ↔ Cabinet', 'status': 'ok' if ok else 'fail', 'message': msg})

    all_comps = [v for k, v in build_dict.items() if v]
    ok, msg = check_psu_wattage(all_comps, ram_quantity)
    results.append({'component': 'PSU Wattage', 'status': 'ok' if ok else 'fail', 'message': msg})

    return results
