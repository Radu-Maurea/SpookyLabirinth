"""
inspect_imc.py
Lists every Input Mapping Context (IMC) in the project, with each key,
the Input Action it triggers, its modifiers and triggers, and the value
each WASD key actually produces after its modifiers run. Used to debug why
W/S don't move the character while A/D do.

How to run (Unreal Output Log, dropdown set to "Cmd"):
    py "E:/UnrealProject/ScareLabirint/inspect_imc.py"
Results appear in the Output Log as LogPython lines.
"""
import unreal

WATCH_KEYS = {"W", "A", "S", "D"}
WATCH_BLUEPRINTS = [
    "/Game/TopDown/Blueprints/BP_TopDownCharacter",
    "/Game/TopDown/Blueprints/BP_TopDownController",
    "/Game/TopDown/Blueprints/BP_TopDownGameMode",
]


def prop(obj, name, default=None):
    """Read an editor property safely (returns default if it doesn't exist)."""
    try:
        return obj.get_editor_property(name)
    except Exception:
        return default


def key_name(key):
    name = prop(key, "key_name")
    return str(name) if name is not None else str(key)


def enum_tail(value):
    """'InputAxisSwizzle.YXZ' -> 'YXZ', 'InputActionValueType.AXIS2D' -> 'AXIS2D'."""
    return str(value).split(".")[-1].upper()


def describe_modifier(mod):
    if mod is None:
        return "NULL MODIFIER (empty slot, breaks this key!)"
    cls = mod.get_class().get_name()
    if "Swizzle" in cls:
        return f"{cls} (order={enum_tail(prop(mod, 'order'))})"
    if "Negate" in cls:
        return f"{cls} (x={prop(mod, 'x')}, y={prop(mod, 'y')}, z={prop(mod, 'z')})"
    return cls


def describe_trigger(trig):
    if trig is None:
        return "NULL TRIGGER"
    return trig.get_class().get_name()


def simulate(mods, value_type):
    """Run a digital key press (1,0,0) through Swizzle/Negate modifiers."""
    v = [1.0, 0.0, 0.0]
    notes = []
    for m in mods:
        if m is None:
            notes.append("null modifier")
            continue
        cls = m.get_class().get_name()
        if "Swizzle" in cls:
            order = enum_tail(prop(m, "order"))
            src = {"X": v[0], "Y": v[1], "Z": v[2]}
            # Swizzle order names which input component lands in X, Y, Z.
            if len(order) == 3 and set(order) <= set("XYZ"):
                v = [src[order[0]], src[order[1]], src[order[2]]]
            else:
                notes.append(f"unknown swizzle order {order}")
        elif "Negate" in cls:
            for i, axis in enumerate("xyz"):
                if prop(m, axis, False):
                    v[i] = -v[i]
        else:
            notes.append(f"{cls} not simulated")
    vt = enum_tail(value_type)
    if "1D" in vt:
        v = [v[0], 0.0, 0.0]
        shown = f"({v[0]:+.0f})"
    elif "2D" in vt:
        shown = f"({v[0]:+.0f}, {v[1]:+.0f})"
    elif "3D" in vt:
        shown = f"({v[0]:+.0f}, {v[1]:+.0f}, {v[2]:+.0f})"
    else:
        shown = "(bool)"
    dead = all(abs(c) < 1e-6 for c in v[:2]) and "BOOL" not in vt
    if dead:
        notes.append("PRODUCES ZERO -> no movement")
    return shown + (f"  [{'; '.join(notes)}]" if notes else "")


def get_mappings(imc):
    # Newer engine versions keep mappings under "default_key_mappings"
    dkm = prop(imc, "default_key_mappings")
    if dkm is not None:
        inner = prop(dkm, "mappings")
        if inner is not None:
            return list(inner)
    old = prop(imc, "mappings")
    return list(old) if old is not None else []


def class_name_of(asset_data):
    try:
        return str(asset_data.asset_class_path.asset_name)
    except Exception:
        return str(prop(asset_data, "asset_class", ""))


registry = unreal.AssetRegistryHelpers.get_asset_registry()
all_assets = registry.get_assets_by_path("/Game", recursive=True)
imc_assets = [a for a in all_assets if class_name_of(a) == "InputMappingContext"]

unreal.log("=" * 70)
unreal.log(f"Found {len(imc_assets)} Input Mapping Context(s)")
actions_seen = {}

for data in imc_assets:
    path = str(data.package_name)
    imc = unreal.load_asset(path)
    unreal.log(f"--- {path} ---")
    for mapping in get_mappings(imc):
        action = prop(mapping, "action")
        action_path = action.get_path_name() if action else "None"
        if action:
            actions_seen[action_path] = action
        k = key_name(prop(mapping, "key"))
        mods = list(prop(mapping, "modifiers") or [])
        trigs = list(prop(mapping, "triggers") or [])
        mod_text = ", ".join(describe_modifier(m) for m in mods) or "no modifiers"
        trig_text = ", ".join(describe_trigger(t) for t in trigs) or "no triggers"
        unreal.log(f"  {k:<14} -> {action_path}")
        unreal.log(f"  {'':<14}    modifiers: {mod_text}")
        unreal.log(f"  {'':<14}    triggers:  {trig_text}")
        if k in WATCH_KEYS and action:
            vt = prop(action, "value_type")
            unreal.log(f"  {'':<14}    <-- WASD: outputs {simulate(mods, vt)} as {enum_tail(vt)}")

unreal.log("--- Input Actions used ---")
for path, action in actions_seen.items():
    mods = ", ".join(describe_modifier(m) for m in (prop(action, "modifiers") or [])) or "none"
    trigs = ", ".join(describe_trigger(t) for t in (prop(action, "triggers") or [])) or "none"
    unreal.log(f"  {path} | value_type={enum_tail(prop(action, 'value_type'))}"
               f" | action modifiers: {mods} | action triggers: {trigs}")

unreal.log("--- Input assets referenced by the TopDown blueprints ---")
input_paths = {str(a.package_name) for a in all_assets
               if class_name_of(a) in ("InputMappingContext", "InputAction")}
for bp in WATCH_BLUEPRINTS:
    try:
        deps = registry.get_dependencies(bp, unreal.AssetRegistryDependencyOptions())
    except Exception as e:
        unreal.log_warning(f"  {bp}: could not read dependencies ({e})")
        continue
    used = sorted(str(d) for d in (deps or []) if str(d) in input_paths)
    unreal.log(f"  {bp}: {', '.join(used) or 'no IMC/IA references'}")
unreal.log("=" * 70)
