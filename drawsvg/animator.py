import math, re, os
import drawsvg as draw

# original svg data
LIGHT_IDS = {
    "right": ["A-right", "B-right", "C-right"],
    "left":  ["A-left",  "B-left",  "C-left"],
}

ORIGINAL_FILLS = {
    "A-right": "#f4eed7", "A-left": "#f4eed7",
    "B-right": "none",    "B-left": "none",
    "C-right": "#d40000", "C-left": "#d40000",
}

#where to piviot
LEVER_PIVOT_LOCAL = (120.4, 49.25)

def read_svg(path):
    # removes extracts between svg tags.
    with open(path) as f:
        txt = f.read()
    m = re.search(r"<svg[^>]*>(.*)</svg>", txt, re.DOTALL)
    if not m:
        raise ValueError("Could not parse SVG")
    inner = m.group(1) #idk if there could be multiple svgs in a svg... but take the first one
    return inner


def inject_into_element(svg, element_id, animate_xml):
    # <tag ... />  -> <tag ...>animate_xml</tag>.
    pattern = re.compile(
                
        r'(<(path|g|circle|ellipse|rect)\b'     # opening tag name
        r'[^>]*?\bid="' + re.escape(element_id) + r'"'  # has our id
        r'[^>]*?)'                                # rest of attributes
        r'\s*/\s*>',                              # self-closing
        re.DOTALL,
    )
    def _repl(m):
        # we match our opening tag. close it, then injecct the animation properties
        # then put the closing tag in, and close it
        # m.group(1) matches the outer parens in the regex. so
        # it will be the element + its old attributes
        # m.group(2) is the inner parens which will match the element name (ie, path or rect,
        # etc)
        return m.group(1) + ">" + animate_xml + "</" + m.group(2) + ">"

    result = pattern.sub(_repl, svg, count=1) # do this sub once
    return result


def inject_into_group(svg, group_id, animate_xml):
    # <group id = ... /> </group> -> <group id = ...>animate_xml</group>.
    pattern = re.compile(
        r'(<g\b[^>]*?\bid="' + re.escape(group_id) + r'"[^>]*?>)',
        re.DOTALL,
    )

    #similar to above. but simpler. we dont need to close it again
    #so we can capture all together
    def _repl(m):
        return m.group(1) + animate_xml

    return pattern.sub(_repl, svg, count=1) # there should only be one group



#these two are copied from what the drawsvg library wouldve done if we used to make it. 
# https://svgwg.org/specs/animations/#KeyTimesAttribute
# but this is an example of how hard it would be from scratch. so we would
# need some sort of interface for building...
def _blink_keyframes(dur, arm_move, tip_hold, n_cycles, blink_half):
    # blinking setup
    # fraction of speed up. sec shouldnt be larger than dur
    # but for some reason it haappens sometimes... :(
    def frac(sec):
        return min(sec / dur, 1.0)

    t_blink_start = arm_move + tip_hold

    key_times = []
    fills = []
    opacities = []

    # Before blinking: original state
    key_times.append(0.0)
    fills.append("ORIG")
    opacities.append("ORIG_OP")

    if t_blink_start > 0:
        key_times.append(frac(t_blink_start))
        fills.append("ORIG")
        opacities.append("ORIG_OP")

    # Blink cycles
    for c in range(n_cycles):
        on  = t_blink_start + c * 2 * blink_half
        mid = on + blink_half
        off = mid + blink_half

        # ON
        key_times.append(frac(on))
        fills.append("#ffaa00")
        opacities.append("0.9")

        key_times.append(frac(mid))
        fills.append("#ffaa00")
        opacities.append("0.9")

        # OFF
        key_times.append(frac(mid))
        fills.append("ORIG")
        opacities.append("ORIG_OP")

        key_times.append(frac(off))
        fills.append("ORIG")
        opacities.append("ORIG_OP")

    # After blinking: rest
    blink_end = t_blink_start + n_cycles * 2 * blink_half + arm_move + 0.5
    key_times.append(1.0)
    fills.append("ORIG")
    opacities.append("ORIG_OP")
    #print(key_times, fills, opacities)
    # basically a mapping to set a fill with opacity at a key time.
    return key_times, fills, opacities


def _lever_keyframes(dur, arm_move, tip_hold, blink_dur, deflection_deg, direction):
    # make lever animation frames
    # self explanitory
    sign = -1 if direction == "left" else 1
    angle = deflection_deg * sign
    cx, cy = LEVER_PIVOT_LOCAL

    def frac(sec):
        return min(sec / dur, 1.0)

    t1 = frac(arm_move)
    t3 = frac(arm_move + tip_hold + blink_dur)
    t4 = frac(arm_move + tip_hold + blink_dur + arm_move)

    kt = [0.0, t1, t3, t4, 1.0]
    # where to move.
    # these are value attributes to the svg element.
    # see the "value" attribute in https://svgwg.org/specs/animations/#ValueAttributes
    # we put these into the <animate> element's value attribute
    vals = [
        f"0 {cx} {cy}",
        f"{angle} {cx} {cy}",
        f"{angle} {cx} {cy}",
        f"0 {cx} {cy}",
        f"0 {cx} {cy}",
    ]
    #print(kt, vals)
    # we join them because the value attribute expects them delimited by a ;
    # "Let values be a list of strings formed by splitting attribute at each U+003B SEMICOLON character."
    return ";".join(f"{k:.4f}" for k in kt), ";".join(vals)


def create_pitman_animation(
    scenario="tip",
    direction="left",
    speed=1.0,
    svg_path="./LichtUebersicht_v4.svg",
):
    # speed constant.
    ARM_MOVE   = 0.3

    if scenario == "tip":
        n_cycles, deflection, tip_hold = 3, 5.0, 0.4
    else:
        n_cycles, deflection, tip_hold = 6, 7.0, 0.0

    
    total_sec = ARM_MOVE + tip_hold + n_cycles + ARM_MOVE + 0.5 # animation time 
    #scale the duration
    # we can leave this out but you just get downtime at the end.
    duration  = total_sec / speed # scale the duration.

    svg_inner = read_svg(svg_path)

    dur_attr = f"{duration:.3f}"

    # 1 we go into each light and add the blinking animations
    blink_side_ids = LIGHT_IDS[direction]
    #print(blink_side_ids)

    for light_id in blink_side_ids:
        orig_fill = ORIGINAL_FILLS[light_id]
        orig_op = "0.1" if orig_fill == "none" else "1"
        if orig_fill == "none":
            orig_fill = "#f4eed7"  # fallback for paths with no fill

        kt_list, fill_list, op_list = _blink_keyframes(
            duration, ARM_MOVE / speed, tip_hold / speed,
            n_cycles , 0.5 / speed,
        )

        # place holders
        fill_vals = [orig_fill if v == "ORIG" else v for v in fill_list]
        op_vals   = [orig_op if v == "ORIG_OP" else v for v in op_list]

        # setup the format for animate element
        kt_str   = ";".join(f"{k:.4f}" for k in kt_list)
        fill_str = ";".join(fill_vals)
        op_str   = ";".join(op_vals)
        # put them in
        animate_xml = (
            f'<animate attributeName="fill" dur="{dur_attr}" '
            f'values="{fill_str}" keyTimes="{kt_str}" '
            f'repeatCount="indefinite" fill="freeze"/>'
            f'<animate attributeName="fill-opacity" dur="{dur_attr}" '
            f'values="{op_str}" keyTimes="{kt_str}" '
            f'repeatCount="indefinite" fill="freeze"/>'
            f'<animate attributeName="stroke-opacity" dur="{dur_attr}" '
            f'values="{op_str.replace("0.9","0.5")}" keyTimes="{kt_str}" '
            f'repeatCount="indefinite" fill="freeze"/>'
        )

        svg_inner = inject_into_element(svg_inner, light_id, animate_xml)

    # 2 go into the lever group and add keytimes
    lever_kt, lever_vals = _lever_keyframes(
        duration, ARM_MOVE / speed, tip_hold / speed,
        n_cycles / speed, deflection, direction,
    )
    # put them in
    lever_anim = (
        f'<animateTransform attributeName="transform" type="rotate" '
        f'dur="{dur_attr}" values="{lever_vals}" keyTimes="{lever_kt}" '
        f'repeatCount="indefinite" fill="freeze"/>'
    )
    svg_inner = inject_into_group(svg_inner, "g825", lever_anim)

    W, H = 800, 500
    
    # making it look nice
    scale = 3.5
    tx = 12
    ty = -35

    print(tx,ty)

    d = draw.Drawing(
        W, H,
        animation_config=draw.types.SyncedAnimationConfig(
            duration=duration,
            show_playback_progress=True,
            show_playback_controls=True,
        ),
    )

    # background
    d.append(draw.Rectangle(0, 0, W, H, fill="#f5f5f0"))

    # move it
    wrapped = (
        f'<g transform="translate({tx:.2f},{ty:.2f}) scale({scale:.4f})">'
        f'{svg_inner}'
        f'</g>'
    )
    d.append(draw.Raw(wrapped))

    # info bar
    d.append(draw.Text(
        f"Scenario: {'Tip' if scenario == 'tip' else 'Direction'}  |  "
        f"Deflection: {deflection}°  |  Cycles: {n_cycles}  |  "
        f"Speed: ×{speed:.1f}  |  Duration: {duration:.1f}s",
        10, 30, H - 14, fill="#888", font_family="sans-serif",
    ))

    return d
